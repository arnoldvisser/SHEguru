import base64
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Store, Invalid, Conflict, empty_state, make_server


def sample():
    data = empty_state()
    data['company']['name'] = 'Test Company'
    data['employees'] = [{'id': 'e1', 'name': 'Test Employee', 'job': 'Supervisor', 'payrollId': '001', 'active': True}]
    data['appointments'] = [{'id': 'a1', 'role': 'First aider', 'employee': 'e1', 'due': '2026-12-01', 'duties': 'Test duties', 'legalBasis': ''}]
    data['training'] = [{'id': 't1', 'employee': 'e1', 'course': 'First aid', 'provider': 'Test Provider', 'due': '2026-12-01', 'completed': False, 'completedOn': ''}]
    return data


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'sheguru.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_persists_on_reopen(self):
        self.store.save(sample(), 0)
        reopened = Store(self.path)
        self.assertEqual(reopened.state()['state'], sample())
        self.assertEqual(reopened.state()['revision'], 1)

    def test_departure_keeps_appointment_and_logs_impact(self):
        self.store.save(sample(), 0)
        changed = sample()
        changed['employees'][0]['active'] = False
        self.store.save(changed, 1)
        self.assertEqual(self.store.state()['state']['appointments'][0]['employee'], 'e1')
        with self.store.connect() as con:
            log = con.execute('SELECT action FROM audit ORDER BY id DESC LIMIT 1').fetchone()[0]
        self.assertIn('1 appointment(s) affected', log)

    def test_conflict_cannot_overwrite_newer_data(self):
        self.store.save(sample(), 0)
        with self.assertRaises(Conflict):
            self.store.save(empty_state(), 0)
        self.assertEqual(self.store.state()['state']['company']['name'], 'Test Company')

    def test_invalid_employee_reference_rolls_back(self):
        bad = sample()
        bad['appointments'][0]['employee'] = 'missing'
        with self.assertRaises(Invalid):
            self.store.save(bad, 0)
        self.assertEqual(self.store.state()['revision'], 0)

    def test_invalid_date_rejected(self):
        bad = sample()
        bad['appointments'][0]['due'] = '2026-02-30'
        with self.assertRaises(Invalid):
            self.store.save(bad, 0)

    def test_duplicate_payroll_ids_rejected(self):
        bad = sample()
        bad['employees'].append({**bad['employees'][0], 'id': 'e2'})
        with self.assertRaises(Invalid):
            self.store.save(bad, 0)

    def test_completed_training_requires_date(self):
        bad = sample()
        bad['training'][0]['completed'] = True
        with self.assertRaises(Invalid):
            self.store.save(bad, 0)
        bad['training'][0]['completedOn'] = '2026-10-21'
        self.assertEqual(self.store.save(bad, 0)['revision'], 1)

    def test_backup_restores_records_files_and_history(self):
        self.store.save(sample(), 0)
        self.store.upload({'name': 'evidence.pdf', 'category': 'Appointment', 'content': base64.b64encode(b'example evidence').decode()})
        backup = self.store.backup()
        restored_path = Path(self.temp.name) / 'restored.sqlite3'
        restored_path.write_bytes(backup)
        restored = Store(restored_path)
        self.assertEqual(restored.state()['state'], sample())
        self.assertEqual(restored.list_files()[0]['name'], 'evidence.pdf')
        with restored.connect() as con:
            self.assertEqual(con.execute('SELECT content FROM attachments').fetchone()[0], b'example evidence')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM audit').fetchone()[0], 2)

    def test_rejects_executable_and_path_uploads(self):
        for name in ('installer.exe', '../record.pdf', 'folder\\record.pdf'):
            with self.assertRaises(Invalid):
                self.store.upload({'name': name, 'category': 'Test', 'content': 'YWJj'})
        self.assertEqual(self.store.list_files(), [])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name) / 'test.sqlite3', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, method=None, headers=None, authenticated=True):
        hs = {'X-SHEguru-Token': self.server.token} if authenticated else {}
        if payload is not None:
            hs['Content-Type'] = 'application/json'
        hs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None,
                                     method=method, headers=hs)
        try:
            return self.client.open(req)
        except urllib.error.HTTPError as response:
            return response

    def test_serves_application_and_token(self):
        with self.request('/', authenticated=False) as r:
            self.assertEqual(r.status, 200)
            self.assertIn(self.server.token.encode(), r.read())
            self.assertIn("script-src 'self'", r.headers['Content-Security-Policy'])
        for asset in ('/app.js', '/style.css'):
            with self.request(asset, authenticated=False) as r:
                self.assertEqual(r.status, 200)

    def test_api_requires_session_token(self):
        with self.request('/api/state', authenticated=False) as r:
            self.assertEqual(r.status, 403)

    def test_cross_origin_and_untrusted_host_rejected(self):
        for headers in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.request('/api/state', headers=headers) as r:
                self.assertEqual(r.status, 403)
        with self.request('/', headers={'Host': 'evil.example'}, authenticated=False) as r:
            self.assertEqual(r.status, 403)

    def test_save_retrieve_conflict_and_invalid_input(self):
        with self.request('/api/state', {'state': sample(), 'revision': 0}, 'PUT') as r:
            self.assertEqual(r.status, 200)
        with self.request('/api/state') as r:
            saved = json.load(r)
            self.assertEqual(saved['state']['company']['name'], 'Test Company')
        with self.request('/api/state', {'state': empty_state(), 'revision': 0}, 'PUT') as r:
            self.assertEqual(r.status, 409)
        with self.request('/api/state', {'state': {}, 'revision': 1}, 'PUT') as r:
            self.assertEqual(r.status, 400)

    def test_document_roundtrip_and_full_backup(self):
        with self.request('/api/documents', {'name': 'signed letter.txt', 'category': 'Appointment', 'content': 'YWJj'}, 'POST') as r:
            self.assertEqual(r.status, 201)
            ident = json.load(r)['id']
        with self.request('/api/documents/' + ident) as r:
            self.assertEqual(r.read(), b'abc')
            self.assertIn('attachment;', r.headers['Content-Disposition'])
        with self.request('/api/backup') as r:
            backup = r.read()
            self.assertTrue(backup.startswith(b'SQLite format 3'))
        with self.request('/api/audit') as r:
            self.assertEqual(len(json.load(r)), 1)

    def test_path_traversal_not_served(self):
        with self.request('/../server.py') as r:
            self.assertEqual(r.status, 404)


if __name__ == '__main__':
    unittest.main()
