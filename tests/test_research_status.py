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
        self.assertFalse(role['supplemental'])
        self.assertEqual(rows['P04']['next_step']['kind'], 'owner_information')
        self.assertEqual(rows['P04']['next_step']['link'], '#portfolio')
        self.assertEqual(rows['G03']['phase2']['open_gates'], ['listed_parent_net_income'])
        self.assertTrue(rows['G03']['phase2']['limitations'][0]['text'])
        self.assertEqual(rows['G03']['role_dispositions'][0]['state'], 'descoped')
        self.assertIn('Worldwide', rows['G03']['role_dispositions'][0]['description'])

    def test_next_step_separates_original_method_from_optional_evidence(self):
        from finance_dashboard.research_status import evidence_next_step
        required={'role':'original','state':'accepted','accepted':True,
                  'supplemental':False,'series_ids':['original.publisher'],
                  'sources_with_observations':1,'owner_input_required':False}
        optional={'role':'additional_deciles','state':'incomplete','accepted':False,
                  'supplemental':True,'series_ids':['extra.publisher'],
                  'sources_with_observations':0,'owner_input_required':False}
        accepted=evidence_next_step('L07','accepted',[required,optional],[])
        self.assertEqual(accepted['kind'],'accepted_with_extensions')
        self.assertEqual(accepted['counts'],{
            'required':1,'required_accepted':1,'supplemental':1,
            'supplemental_accepted':0,'descoped':0})
        self.assertEqual(accepted['role_ids'],[])
        # A failed original role still blocks, regardless of optional progress.
        original_missing={**required,'accepted':False,
                          'state':'blocked','sources_with_observations':0}
        blocked=evidence_next_step('L07','incomplete',[original_missing,optional],
                                   ['original'])
        self.assertEqual(blocked['kind'],'publisher_data')
        self.assertEqual(blocked['link'],'#research-sources')
        self.assertEqual(blocked['role_ids'],['original'])
        self.assertEqual(blocked['counts']['required_accepted'],0)

    def test_owner_information_is_asked_for_only_if_it_is_actually_missing(self):
        from finance_dashboard.research_status import evidence_next_step
        owner={'role':'owner_allocation','state':'user_input','accepted':False,
               'supplemental':False,'series_ids':[],
               'sources_with_observations':0,'owner_input_required':True}
        owner_step=evidence_next_step('P04','conditional',[owner],[])
        self.assertEqual(owner_step['kind'],'owner_information')
        self.assertEqual(owner_step['link'],'#portfolio')
        self.assertIn('Your own information',owner_step['message'])
        supplied=evidence_next_step('P04','accepted',[{**owner,'accepted':True,
                                                       'owner_input_required':False}],[])
        self.assertEqual(supplied['kind'],'ready')
        self.assertIsNone(supplied['link'])
        no_mapping=evidence_next_step('G03','deferred',[{**owner,
            'state':'incomplete','owner_input_required':False}],['original'])
        self.assertEqual(no_mapping['kind'],'original_research')
        self.assertIsNone(no_mapping['link'])
        self.assertNotIn('Your',no_mapping['message'])
        reassessment=evidence_next_step('G03','not_checked',[],[])
        self.assertEqual(reassessment['kind'],'assessment_pending')
        self.assertIsNone(reassessment['link'])

    def test_debug_workplan_preserves_only_evaluated_next_actions(self):
        from finance_dashboard.research_status import research_next_actions
        self.assertEqual(research_next_actions(None, {'analyses': []})['status'],
                         'assessment_unavailable')
        self.assertEqual(research_next_actions(None, {'analyses': []})['questions'], [])
        document={'analyses':[
            {'id':'P04','title':'Portfolio sensitivity','comparison_contract':{
                'original_requirements':[{'role':'weights','description':'Owner weights',
                                          'supply':'user'}]}},
            {'id':'G03','title':'Global listed profits','comparison_contract':{
                'original_requirements':[{'role':'profit_scope','description':
                    'Consolidated parent profits','series_ids':[]}]}}],
            'original_sources':[]}
        snapshot=AcceptanceSnapshot(datetime(2026,11,15,tzinfo=timezone.utc),{
            'P04': {'state':'conditional','requirements':[
                {'role':'weights','state':'user_input','accepted':False,
                 'series_ids':[],'limitations':[]}],
                'limitations':[],'blocking_roles':[]},
            'G03': {'state':'deferred','requirements':[
                {'role':'profit_scope','state':'incomplete','accepted':False,
                 'series_ids':[],'limitations':[]}],
                'limitations':[],'blocking_roles':['profit_scope']},
        })
        report=research_next_actions(snapshot,document)
        self.assertEqual(report['status'],'ready')
        self.assertEqual(report['question_count'],2)
        by_id={r['id']:r for r in report['questions']}
        self.assertEqual(by_id['P04']['next_step']['kind'],'owner_information')
        self.assertEqual(by_id['G03']['next_step']['kind'],'original_research')
        self.assertIsNone(by_id['G03']['next_step']['link'])
        self.assertEqual(report['next_action_counts'],{
            'owner_information':1,'original_research':1})
        self.assertEqual(by_id['G03']['blocking_role_evidence'], [{
            'role': 'profit_scope',
            'series_ids': [],
            'sources_with_observations': 0,
            'blocking_checks': [],
            'blocking_reasons': [],
            'original_source_proof': None,
        }])

    def test_debug_report_exposes_exact_gate_reason_without_new_evaluation(self):
        from finance_dashboard.research_status import research_next_actions
        document={'analyses':[{'id':'C07','title':'Consumer inflation',
            'comparison_contract':{'original_requirements':[
                {'role':'copper','description':'Publisher copper price'}]}}],
            'original_sources': []}
        snapshot=AcceptanceSnapshot(datetime(2026,11,15,tzinfo=timezone.utc),{
            'C07':{'state':'incomplete','requirements':[
                {'role':'copper','state':'incomplete','accepted':False,
                 'series_ids':['prices.commodity.copper_usd'],
                 'sources_with_observations':802,
                 'blocking_checks':['original_source_values'],
                 'checks':[{'id':'original_source_values','state':'incomplete',
                            'code':'verified_source_values_required'}],
                 'limitations':[]}],
                 'blocking_roles':['copper'],'limitations':[]},
        })
        report=research_next_actions(snapshot,document)
        blockers=report['questions'][0]['blocking_role_evidence']
        self.assertEqual(blockers[0]['role'],'copper')
        self.assertEqual(blockers[0]['sources_with_observations'],802)
        self.assertEqual(blockers[0]['blocking_reasons'],[{
            'id':'original_source_values','state':'incomplete',
            'code':'verified_source_values_required', 'series_ids':[]}])
        self.assertEqual(blockers[0]['original_source_proof'], {
            'state': 'incomplete', 'code': 'verified_source_values_required',
            'unverified_series_ids': [],
        })
        report_with_coverage = research_next_actions(snapshot, document, [
            {'id': 'prices.commodity.copper_usd', 'stored_periods': 802}])
        self.assertEqual(report_with_coverage['questions'][0]
                         ['blocking_role_evidence'][0]['stored_source_periods'],
                         {'prices.commodity.copper_usd': 802})

    def test_unassessed_question_is_not_reported_as_accepted(self):
        snapshot = AcceptanceSnapshot(datetime(2026, 11, 11, tzinfo=timezone.utc), {})
        report = research_status(snapshot, {'analyses': [{'id': 'C01', 'title': 'Growth'}]})
        self.assertEqual(report['counts'], {'not_checked': 1})
        self.assertEqual(report['questions'][0]['state'], 'not_checked')
        self.assertEqual(report['questions'][0]['role_dispositions'], [])

