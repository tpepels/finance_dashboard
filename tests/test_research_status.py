"""Research navigation must preserve scientific and personal-input boundaries."""
from datetime import datetime, timezone
import unittest

from finance_dashboard.engine.acceptance import AcceptanceSnapshot
from finance_dashboard.research_status import research_status


class ResearchStatusTests(unittest.TestCase):
    def test_counts_roles_and_owner_requirements_come_from_current_assessment(self):
        document = {'analyses': [
            {'id': 'P04', 'title': 'Portfolio sensitivity', 'comparison_contract': {
                'original_requirements': [{'role': 'weights', 'description': 'Declared allocation', 'supply': 'user'}]}},
            {'id': 'G03', 'title': 'Listed profits', 'descoped_roles': [
                {'role': 'universe', 'reason': 'Worldwide parent coverage is unavailable.'}]}], 'original_sources': []}
        snapshot = AcceptanceSnapshot(datetime(2026, 11, 11, tzinfo=timezone.utc), {
            'P04': {'state': 'conditional', 'requirements': [
                {'role': 'weights', 'state': 'user_input', 'accepted': False, 'series_ids': [], 'limitations': []}],
                'limitations': [], 'blocking_roles': []},
            'G03': {'state': 'deferred', 'requirements': [], 'blocking_roles': ['listed_parent_net_income'],
                'limitations': [{'code': 'deferred_research_extension', 'detail': 'Original method withheld.'}]}})
        report = research_status(snapshot, document)
        self.assertEqual(report['counts'], {'conditional': 1, 'deferred': 1})
        rows = {r['analysis_id']: r for r in report['questions']}
        role = rows['P04']['role_dispositions'][0]
        self.assertEqual(role['description'], 'Declared allocation')
        self.assertTrue(role['owner_input_required'])
        self.assertFalse(role['accepted'])
        self.assertEqual(rows['G03']['phase2']['open_gates'], ['listed_parent_net_income'])
        self.assertTrue(rows['G03']['phase2']['limitations'][0]['text'])
        self.assertEqual(rows['G03']['role_dispositions'][0]['state'], 'descoped')
        self.assertIn('Worldwide', rows['G03']['role_dispositions'][0]['description'])

    def test_unassessed_question_is_not_reported_as_accepted(self):
        snapshot = AcceptanceSnapshot(datetime(2026, 11, 11, tzinfo=timezone.utc), {})
        report = research_status(snapshot, {'analyses': [{'id': 'C01', 'title': 'Growth'}]})
        self.assertEqual(report['counts'], {'not_checked': 1})
        self.assertEqual(report['questions'][0]['state'], 'not_checked')
        self.assertEqual(report['questions'][0]['role_dispositions'], [])

