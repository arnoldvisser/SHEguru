"""Document filing, old-schema upgrades and blank-template delivery."""
import json
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from server import Store, Invalid, empty_state, ROOT
import test_server

sample = test_server.sample


class DocumentSectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'documents.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_upload_section_and_refiling_preserve_content_links_and_backup(self):
        ident = self.store.upload({'name': 'letter.txt', 'category': 'Signed', 'content': 'YWJj', 'section': 'appointment'})['id']
        state = sample()
        state['requirements'][0].update(document=ident, appointment='a1', evidenceEmployee='e1')
        self.store.save(state, 0)
        self.assertEqual(self.store.list_files()[0]['section'], 'appointment')
        self.store.file_section(ident, 'document')
        self.assertEqual(self.store.list_files()[0]['section'], 'document')
        self.assertEqual(self.store.state()['state']['requirements'][0]['document'], ident)
        restored = Path(self.temp.name) / 'backup.sqlite3'
        restored.write_bytes(self.store.backup())
        self.assertEqual(Store(restored).list_files()[0]['section'], 'document')
        with self.store.connect() as con:
            self.assertEqual(con.execute('SELECT content FROM attachments').fetchone()[0], b'abc')
            self.assertIn('Legal documents', con.execute('SELECT action FROM audit ORDER BY id DESC LIMIT 1').fetchone()[0])

    def test_invalid_sections_do_not_modify_documents(self):
        ident = self.store.upload({'name': 'old.txt', 'category': 'Existing', 'content': 'YWJj'})['id']
        for section in ('other', '', None):
            with self.subTest(section=section), self.assertRaises(Invalid):
                self.store.file_section(ident, section)
        with self.assertRaises(Invalid):
            self.store.upload({'name': 'bad.txt', 'category': 'Test', 'content': 'YWJj', 'section': 'bad'})
        self.assertEqual(self.store.list_files()[0]['section'], 'unfiled')
        self.assertEqual(len(self.store.list_files()), 1)

    def test_old_attachment_schema_is_upgraded_without_losing_file(self):
        old_path = Path(self.temp.name) / 'old.sqlite3'
        with sqlite3.connect(old_path) as con:
            con.execute('CREATE TABLE attachments (id TEXT PRIMARY KEY,name TEXT,category TEXT,uploaded_at TEXT,size INTEGER,sha256 TEXT,content BLOB)')
            con.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)', ('a'*32, 'old.txt', 'Saved letter', '2026-01-01', 3, 'hash', b'abc'))
        upgraded = Store(old_path)
        self.assertEqual(upgraded.list_files()[0]['name'], 'old.txt')
        self.assertEqual(upgraded.list_files()[0]['section'], 'unfiled')
        with upgraded.connect() as con:
            self.assertEqual(con.execute('SELECT content FROM attachments').fetchone()[0], b'abc')
        self.assertEqual(Store(old_path).list_files(), upgraded.list_files())

    def test_new_checklist_items_added_once_without_resetting_decisions(self):
        old = empty_state()
        old['requirements'] = [r for r in old['requirements'] if r['id'] not in ('document-19', 'document-20')]
        old['requirements'][0].update(applicability='excluded', reason='Keep my decision')
        next(r for r in old['requirements'] if r['id'] == 'document-2')['name'] = 'Workplace hazard identification and risk assessments'
        next(r for r in old['requirements'] if r['id'] == 'document-5')['name'] = 'My customised committee record'
        with self.store.connect() as con:
            con.execute('UPDATE workspace SET payload=?', (json.dumps(old),))
        result = self.store.state()['state']
        self.assertEqual(len(result['requirements']), 36)
        self.assertEqual(result['requirements'][0]['reason'], 'Keep my decision')
        self.assertEqual(next(r for r in result['requirements'] if r['id'] == 'document-2')['name'], 'Standard risk assessment document')
        self.assertEqual(next(r for r in result['requirements'] if r['id'] == 'document-5')['name'], 'My customised committee record')
        self.store.save(result, 0)
        self.assertEqual(len(Store(self.path).state()['state']['requirements']), 36)


class DocumentSectionHTTPTests(unittest.TestCase):
    setUp = test_server.HTTPTests.setUp
    tearDown = test_server.HTTPTests.tearDown
    request = test_server.HTTPTests.request

    def test_template_downloads_do_not_complete_any_requirement(self):
        before = self.server.store.state()
        with self.request('/api/templates') as response:
            self.assertEqual(response.status, 200)
            catalogue = json.load(response)
        self.assertEqual(len(catalogue), 29)
        self.assertEqual({row['requirement'] for row in catalogue if row['section'] == 'appointment'},
                         {row['id'] for row in before['state']['requirements'] if row['kind'] == 'appointment'})
        expected_legal = {'investigation-report.txt', 'risk-assessment.csv', 'root-cause-analysis.txt',
                          'vehicle-inspection.csv', 'ppe-inspection.csv', 'hand-tool-inspection.csv',
                          'electric-tool-inspection.csv', 'ladder-inspection.csv', 'section-37-2-agreement.txt'}
        self.assertTrue(expected_legal <= {row['file'] for row in catalogue if row['section'] == 'document'})
        for row in catalogue:
            name = row['file']
            with self.subTest(name=name), self.request('/api/templates/' + name) as r:
                self.assertEqual(r.status, 200)
                self.assertGreater(len(r.read()), 100)
                self.assertIn('attachment;', r.headers['Content-Disposition'])
        self.assertEqual(self.server.store.state(), before)
        self.assertEqual(self.server.store.list_files(), [])
        with self.request('/api/templates/policy.txt', authenticated=False) as r:
            self.assertEqual(r.status, 403)
        for path in ('/api/templates/server.py', '/api/templates/catalogue.json', '/api/templates/nested/policy.txt'):
            with self.subTest(path=path), self.request(path) as r:
                self.assertEqual(r.status, 404)
        with self.request('/api/templates', authenticated=False) as r:
            self.assertEqual(r.status, 403)

    def test_inspection_templates_have_distinct_checks_and_blank_findings(self):
        checklists = []
        for name in ('vehicle-inspection.csv', 'ppe-inspection.csv', 'hand-tool-inspection.csv', 'electric-tool-inspection.csv', 'ladder-inspection.csv'):
            with (ROOT / 'templates' / name).open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rows), 10)
            self.assertTrue(all(row['Check item'] and row['Inspection criterion'] for row in rows))
            self.assertTrue(all(row['Finding (OK / Defect / Not applicable)'] == '' for row in rows))
            self.assertTrue(all(row['Inspector'] == '' and row['Released for use by / date'] == '' for row in rows))
            checklists.append(tuple(row['Check item'] for row in rows))
        self.assertEqual(len(set(checklists)), 5)

    def test_refiling_endpoint(self):
        with self.request('/api/documents', {'name': 'policy.txt', 'category': 'Policy', 'section': 'document', 'content': 'YWJj'}, 'POST') as r:
            self.assertEqual(r.status, 201)
            ident = json.load(r)['id']
        with self.request('/api/documents/' + ident + '/section', {'section': 'appointment'}, 'POST') as r:
            self.assertEqual(r.status, 200)
        with self.request('/api/documents') as r:
            self.assertEqual(json.load(r)[0]['section'], 'appointment')
        with self.request('/api/documents/' + ident + '/section', {'section': 'document'}, 'POST', authenticated=False) as r:
            self.assertEqual(r.status, 403)


if __name__ == '__main__':
    unittest.main()
