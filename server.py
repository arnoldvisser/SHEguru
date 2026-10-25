"""SHEguru single-user laptop server. Python 3.10+, no external dependencies."""
import argparse
from contextlib import contextmanager
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, quote

ROOT = Path(__file__).resolve().parent
MAX_REQUEST = 16 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
GROUPS = ('employees', 'appointments', 'training', 'tasks', 'requirements')


def starter_requirements():
    return json.loads((ROOT / 'requirements.json').read_text())


def migrate(state):
    # Add the checklist without changing existing records or attachment data.
    if 'requirements' not in state:
        state['requirements'] = starter_requirements()
    return state


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def empty_state():
    return {'schemaVersion': 1, 'company': {'name': '', 'industry': '', 'location': ''},
            **{key: [] for key in GROUPS}, 'requirements': starter_requirements()}


class Invalid(ValueError):
    pass


class Conflict(Exception):
    pass


def text(value, name, required=False, limit=2000):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise Invalid(f'Please supply a valid {name}.')
    return value


def date(value, name):
    text(value, name, True, 10)
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        dt.date.fromisoformat(value)
    except ValueError:
        raise Invalid(f'Please supply a valid {name}.') from None


def validate(state):
    if not isinstance(state, dict) or state.get('schemaVersion') != 1:
        raise Invalid('This is not a supported SHEguru workspace.')
    company = state.get('company')
    if not isinstance(company, dict):
        raise Invalid('Company details are missing.')
    for field in ('name', 'industry', 'location'):
        text(company.get(field), f'company {field}', limit=200)
    for key in GROUPS:
        items = state.get(key)
        if not isinstance(items, list) or len(items) > 10000:
            raise Invalid(f'Invalid {key} records.')
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise Invalid(f'Invalid {key} record.')
            ident = text(item.get('id'), 'record ID', True, 80)
            if not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in seen:
                raise Invalid('Record IDs must be unique and valid.')
            seen.add(ident)
    people = {e['id'] for e in state['employees']}
    payroll_ids = set()
    for e in state['employees']:
        text(e.get('name'), 'employee name', True, 200)
        text(e.get('job'), 'job title', limit=200)
        text(e.get('payrollId'), 'payroll ID', limit=100)
        if e['payrollId']:
            if e['payrollId'].casefold() in payroll_ids:
                raise Invalid('Payroll IDs must be unique.')
            payroll_ids.add(e['payrollId'].casefold())
        if type(e.get('active')) is not bool:
            raise Invalid('Invalid employee status.')
    for key in ('appointments', 'training'):
        for item in state[key]:
            field = 'role' if key == 'appointments' else 'course'
            text(item.get(field), field, True, 200)
            date(item.get('due'), 'due date')
            employee = text(item.get('employee'), 'employee reference', limit=80)
            if (key == 'training' and not employee) or (employee and employee not in people):
                raise Invalid('The selected employee does not exist.')
            if key == 'appointments':
                text(item.get('duties'), 'appointment duties', limit=5000)
                text(item.get('legalBasis'), 'legal basis', limit=500)
            else:
                if type(item.get('completed')) is not bool:
                    raise Invalid('Invalid training status.')
                text(item.get('provider'), 'training provider', limit=200)
                completed_on = item.get('completedOn')
                if completed_on:
                    date(completed_on, 'completion date')
                elif completed_on != '':
                    raise Invalid('Invalid completion date.')
                if item['completed'] != bool(completed_on):
                    raise Invalid('Completed training needs a completion date.')
    for item in state['tasks']:
        text(item.get('name'), 'reminder title', True, 200)
        date(item.get('due'), 'reminder date')
        if type(item.get('done')) is not bool:
            raise Invalid('Invalid reminder status.')
    for item in state['requirements']:
        if item.get('kind') not in ('appointment', 'document'):
            raise Invalid('Invalid requirement kind.')
        text(item.get('name'), 'requirement title', True, 200)
        for key, limit in (('legalBasis', 500), ('condition', 2000), ('reason', 2000), ('notes', 5000)):
            text(item.get(key), key, limit=limit)
        if item.get('applicability') not in ('pending', 'required', 'excluded'):
            raise Invalid('Invalid applicability.')
        if item['applicability'] == 'excluded' and not item['reason'].strip():
            raise Invalid('Explain why this requirement does not apply.')
        for key in ('appointment', 'document', 'evidenceEmployee'):
            text(item.get(key), key, limit=80)
        if item['appointment'] and item['appointment'] not in {a['id'] for a in state['appointments']}:
            raise Invalid('Appointment reference does not exist.')
        if item['evidenceEmployee'] and item['evidenceEmployee'] not in people:
            raise Invalid('Evidence employee reference does not exist.')
        if item['kind'] == 'document' and (item['appointment'] or item['evidenceEmployee']):
            raise Invalid('Company documents cannot refer to an appointment.')
        if item.get('due'):
            date(item['due'], 'requirement review date')
        elif item.get('due') != '':
            raise Invalid('Invalid requirement review date.')
    return state


def summary(before, after):
    changes = []
    if before['company'] != after['company']:
        changes.append('Company details updated')
    for key in GROUPS:
        previous = {x['id']: x for x in before[key]}
        current = {x['id']: x for x in after[key]}
        added, removed = current.keys() - previous.keys(), previous.keys() - current.keys()
        updated = [i for i in current.keys() & previous.keys() if current[i] != previous[i]]
        if added:
            changes.append(f'{len(added)} {key} added')
        if removed:
            changes.append(f'{len(removed)} {key} removed')
        if updated:
            changes.append(f'{len(updated)} {key} updated')
        if key == 'employees':
            for ident in updated:
                if previous[ident]['active'] and not current[ident]['active']:
                    name = current[ident]['name']
                    gaps = sum(a['employee'] == ident for a in after['appointments'])
                    changes.append(f'{name} marked as left; {gaps} appointment(s) affected')
    return '; '.join(changes) or 'Workspace saved'


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS workspace
                (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit
                (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, action TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attachments
                (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
                 uploaded_at TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, content BLOB NOT NULL);
            ''')
            con.execute('INSERT OR IGNORE INTO workspace VALUES(1,0,?)', (json.dumps(empty_state()),))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def state(self):
        with self.connect() as con:
            row = con.execute('SELECT * FROM workspace WHERE id=1').fetchone()
            return {'revision': row['revision'], 'state': migrate(json.loads(row['payload']))}

    def save(self, state, revision):
        if not isinstance(state, dict):
            raise Invalid('Invalid workspace.')
        if 'requirements' not in state:
            raise Invalid('Reopen SHEguru to load the requirements checklist before saving.')
        validate(state)
        if type(revision) is not int:
            raise Invalid('Missing workspace revision.')
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM workspace WHERE id=1').fetchone()
            if row['revision'] != revision:
                raise Conflict('Another tab changed these records. Reload and try again.')
            before = migrate(json.loads(row['payload']))
            # Old tabs must not silently discard a checklist created by a newer client.
            if before['requirements'] and not state['requirements']:
                raise Invalid('The requirements checklist cannot be removed.')
            file_ids = {r[0] for r in con.execute('SELECT id FROM attachments')}
            for requirement in state['requirements']:
                if requirement['document'] and requirement['document'] not in file_ids:
                    raise Invalid('The evidence document does not exist.')
            action = summary(before, state)
            con.execute('UPDATE workspace SET revision=revision+1,payload=? WHERE id=1', (json.dumps(state),))
            con.execute('INSERT INTO audit(timestamp,action) VALUES(?,?)', (now(), action))
        return self.state()

    def list_files(self):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT id,name,category,uploaded_at,size,sha256 FROM attachments ORDER BY uploaded_at DESC')]

    def upload(self, payload):
        name = text(payload.get('name'), 'file name', True, 250)
        category = text(payload.get('category'), 'document category', True, 100)
        if '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
            raise Invalid('Use a simple file name without folders.')
        if Path(name).suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg', '.txt', '.csv', '.docx', '.xlsx'}:
            raise Invalid('Supported files: PDF, images, TXT, CSV, DOCX and XLSX.')
        try:
            content = base64.b64decode(payload.get('content', ''), validate=True)
        except (ValueError, TypeError):
            raise Invalid('Invalid file data.') from None
        if not content or len(content) > MAX_FILE:
            raise Invalid('Choose a file between 1 byte and 10 MB.')
        ident = secrets.token_hex(16)
        with self.lock, self.connect() as con:
            con.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)',
                        (ident, name, category, now(), len(content), hashlib.sha256(content).hexdigest(), content))
            con.execute('INSERT INTO audit(timestamp,action) VALUES(?,?)', (now(), f'Document uploaded: {name}'))
        return {'id': ident}

    def backup(self):
        # A SQLite online backup captures state, audit and uploaded files in one consistent snapshot.
        with self.lock, self.connect() as source, sqlite3.connect(':memory:') as target:
            source.backup(target)
            return target.serialize()


class Handler(BaseHTTPRequestHandler):
    server_version = 'SHEguru/0.3'

    def log_message(self, fmt, *args):
        # Do not log request bodies, employee records or session tokens.
        pass

    def send(self, status, body, content_type='application/json; charset=utf-8', extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def guard(self, api=False):
        port = self.server.server_port
        host = self.headers.get('Host', '')
        if host not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
            self.send(403, {'error': 'Open SHEguru using its local laptop address.'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
            self.send(403, {'error': 'Cross-site requests are not permitted.'})
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send(403, {'error': 'Cross-site requests are not permitted.'})
            return False
        if api and not secrets.compare_digest(self.headers.get('X-SHEguru-Token', ''), self.server.token):
            self.send(403, {'error': 'Reopen SHEguru to refresh your session.'})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.guard(path.startswith('/api/')):
            return
        if path in ('/', '/index.html'):
            html = (ROOT / 'web/index.html').read_text().replace('__CSRF_TOKEN__', self.server.token)
            self.send(200, html, 'text/html; charset=utf-8')
        elif path in ('/app.js', '/style.css'):
            content_type = 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8'
            self.send(200, (ROOT / 'web' / path[1:]).read_bytes(), content_type)
        elif path == '/api/state':
            self.send(200, self.server.store.state())
        elif path == '/api/documents':
            self.send(200, self.server.store.list_files())
        elif path == '/api/audit':
            with self.server.store.connect() as con:
                self.send(200, [dict(r) for r in con.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500')])
        elif path == '/api/backup':
            name = 'SHEguru-backup-' + dt.date.today().isoformat() + '.sqlite3'
            self.send(200, self.server.store.backup(), 'application/octet-stream',
                      {'Content-Disposition': f'attachment; filename="{name}"'})
        elif re.fullmatch(r'/api/documents/[a-f0-9]{32}', path):
            with self.server.store.connect() as con:
                row = con.execute('SELECT * FROM attachments WHERE id=?', (path.rsplit('/', 1)[1],)).fetchone()
            if row:
                self.send(200, row['content'], 'application/octet-stream',
                          {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['name'], safe='')})
            else:
                self.send(404, {'error': 'Document not found.'})
        else:
            self.send(404, {'error': 'Not found.'})

    def mutate(self, method):
        if not self.guard(True):
            return
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_REQUEST:
                raise Invalid('Request is empty or too large.')
            if self.headers.get_content_type() != 'application/json':
                raise Invalid('Expected JSON data.')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise Invalid('Expected a JSON object.')
            if method == 'PUT' and path == '/api/state':
                self.send(200, self.server.store.save(payload.get('state'), payload.get('revision')))
            elif method == 'POST' and path == '/api/documents':
                self.send(201, self.server.store.upload(payload))
            else:
                self.send(404, {'error': 'Not found.'})
        except Conflict as exc:
            self.send(409, {'error': str(exc)})
        except (Invalid, ValueError, TypeError, KeyError):
            self.send(400, {'error': 'Invalid data. Check all required fields, dates and references.'})
        except sqlite3.Error:
            self.send(500, {'error': 'Could not save to the database. Check disk space and folder permissions.'})

    def do_PUT(self):
        self.mutate('PUT')

    def do_POST(self):
        self.mutate('POST')


def make_server(database, port=8765):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.store = Store(database)
    server.token = secrets.token_urlsafe(32)
    return server


def main():
    parser = argparse.ArgumentParser(description='Run SHEguru on this laptop.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = make_server(args.data_dir / 'sheguru.sqlite3', args.port)
    except OSError as exc:
        print(f'Could not start SHEguru: {exc}\nIf SHEguru is already running, open http://127.0.0.1:{args.port}')
        return 1
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'\nSHEguru laptop edition\nOpen: {url}\nRecords: {server.store.path}\nKeep this window open. Press Ctrl+C to stop.\n', flush=True)
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nSHEguru stopped. Your saved records remain in the data folder.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
