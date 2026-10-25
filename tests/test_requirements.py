"""Checklist migration, references, persistence and backup regression tests."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from server import Store, Invalid, empty_state
from test_server import sample


class RequirementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_starter_covers_both_kinds_without_assuming_applicability(self):
        rows = self.store.state()['state']['requirements']
        self.assertEqual(len(rows), 36)
        self.assertEqual({r['kind'] for r in rows}, {'appointment', 'document'})
        self.assertTrue(all(r['applicability'] == 'pending' and r['condition'] and r['legalBasis'] for r in rows))

    def test_old_database_gets_checklist_without_losing_records_or_files(self):
        old = sample()
        del old['requirements']
        with self.store.connect() as con:
            con.execute('UPDATE workspace SET payload=?,revision=7', (json.dumps(old),))
        ident = self.store.upload({'name': 'old.pdf', 'category': 'Existing', 'content': 'YWJj'})['id']
        reopened = Store(self.path)
        result = reopened.state()
        self.assertEqual(result['revision'], 7)
        self.assertEqual(result['state']['appointments'], old['appointments'])
        self.assertEqual(result['state']['employees'], old['employees'])
        self.assertEqual(len(result['state']['requirements']), 36)
        self.assertEqual(reopened.list_files()[0]['id'], ident)
        reopened.save(result['state'], 7)
        self.assertEqual(reopened.state()['revision'], 8)

    def test_linked_signed_evidence_and_notes_survive_backup(self):
        state = sample()
        ident = self.store.upload({'name': 'signed.pdf', 'category': 'Signed letter', 'content': base64.b64encode(b'%PDF-test').decode()})['id']
        r = state['requirements'][0]
        r.update(applicability='required', appointment='a1', document=ident, evidenceEmployee='e1', notes='Signed by both parties', due='2027-01-01')
        self.store.save(state, 0)
        restored_path = Path(self.temp.name) / 'backup.sqlite3'
        restored_path.write_bytes(self.store.backup())
        restored = Store(restored_path)
        self.assertEqual(restored.state()['state']['requirements'][0], r)
        self.assertEqual(restored.list_files()[0]['id'], ident)
        with restored.connect() as con:
            self.assertIn('requirements updated', con.execute('SELECT action FROM audit ORDER BY id DESC LIMIT 1').fetchone()[0])

    def test_missing_or_unrelated_references_rejected(self):
        for update in ({'appointment': 'missing'}, {'document': 'f' * 32}, {'evidenceEmployee': 'missing'}, {'due': '2026-02-30'}, {'applicability': 'excluded', 'reason': '   '}):
            with self.subTest(update=update):
                state = sample()
                state['requirements'][0].update(update)
                with self.assertRaises(Invalid):
                    self.store.save(state, 0)
        self.assertEqual(self.store.state()['revision'], 0)

    def test_not_applicable_requires_reason_and_is_preserved(self):
        state = sample()
        state['requirements'][5].update(applicability='excluded', reason='Office only; no construction work')
        self.store.save(state, 0)
        self.assertEqual(self.store.state()['state']['requirements'][5]['reason'], 'Office only; no construction work')

    def test_legacy_client_cannot_overwrite_checklist(self):
        state = sample()
        state['requirements'][0]['notes'] = 'Keep this decision'
        self.store.save(state, 0)
        legacy = sample()
        del legacy['requirements']
        with self.assertRaises(Invalid):
            self.store.save(legacy, 1)
        self.assertEqual(self.store.state()['state']['requirements'][0]['notes'], 'Keep this decision')


if __name__ == '__main__':
    unittest.main()
