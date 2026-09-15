import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from calculators.campaign import CampaignSession, CampaignStateDelta, OrganizationRecord, RelationshipRecord


class CampaignTransactionTests(unittest.TestCase):
    def test_edit_save_reload_and_undo(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'campaign.json'
            session = CampaignSession(autosave_path=path)
            session.upsert_record(OrganizationRecord('o', 'Guild', resources=10))
            self.assertEqual(CampaignSession.load_or_new(path).organizations['o'].resources, 10)
            session.apply(CampaignStateDelta(organization_resource_changes={'o': -2}))
            self.assertEqual(session.organizations['o'].resources, 8)
            session.undo()
            self.assertEqual(session.organizations['o'].resources, 10)
            session.undo()
            self.assertEqual(session.organizations, {})

    def test_failed_save_does_not_apply_or_lose_undo(self):
        session = CampaignSession()
        session.upsert_record(RelationshipRecord('r', 'a', 'b'))
        before = session.to_dict()
        with patch.object(CampaignSession, 'save', side_effect=OSError('disk')):
            with self.assertRaises(OSError): session.apply(CampaignStateDelta(relationship_changes={'r': 1}))
            self.assertEqual(session.to_dict(), before)
            with self.assertRaises(OSError): session.undo()
            self.assertEqual(session.to_dict(), before)
        self.assertTrue(session.undo())

    def test_unknown_participant_is_not_silently_ignored(self):
        session = CampaignSession()
        with self.assertRaises(ValueError): session.apply(CampaignStateDelta(force_losses={'missing': 20}))
        self.assertEqual(session.history, [])

    def test_structurally_invalid_file_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'campaign.json'
            path.write_text('{"schema":"gurps-calculadora.campaign.v1","characters":{"x":4}}', encoding='utf-8')
            session = CampaignSession.load_or_new(path)
            self.assertTrue(session.recovered_file.exists())
