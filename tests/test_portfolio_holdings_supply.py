"""Actual holdings supply only the dated role they can establish."""
import unittest
from finance_dashboard.owner_supply import supplied_roles


class PortfolioSupplyTests(unittest.TestCase):
    def test_dated_owner_holdings_are_not_classified_as_a_curated_event_register(self):
        from finance_dashboard.research_acceptance import analysis_acceptance
        from finance_dashboard.research_corpus import load_research_corpus
        definition = next(a for a in load_research_corpus()['analyses'] if a['id'] == 'P01')
        portfolio = {'as_of': '2025-12-31', 'scope': 'full_invested_portfolio',
                     'positions': [{'isin': 'US0378331005', 'identity_source': 'owner'}],
                     'summary': {'total_value_eur': 60}}
        result = analysis_acceptance(definition, {}, {}, [], observations_checked=False,
                                     owner_supply=supplied_roles(None, [], portfolio=portfolio))
        role = next(r for r in result['requirements'] if r['role'] == 'portfolio_fund_weights')
        self.assertEqual(role['checks'][0]['code'], 'owner_inputs_supplied')
        self.assertEqual(role['checks'][0]['supplied_by'], 'portfolio_holdings')

    def test_undated_or_partial_holdings_do_not_certify_complete_fund_weights(self):
        portfolio = {'as_of': None, 'combine_accounts': True, 'scope': 'listed_positions',
                     'positions': [{'isin': 'US0378331005', 'identity_source': 'owner'}],
                     'summary': {'total_value_eur': 60}}
        self.assertNotIn(('P01', 'portfolio_fund_weights'), supplied_roles(None, [], portfolio=portfolio))
        dated = {**portfolio, 'as_of': '2025-12-31', 'scope': 'full_invested_portfolio'}
        roles = supplied_roles(None, [], portfolio=dated)
        self.assertEqual(roles[('P01', 'portfolio_fund_weights')]['supplied_by'], 'portfolio_holdings')
        self.assertNotIn(('P05', 'actual_weights'), roles)
        self.assertNotIn(('P04', 'currency_portfolio_weights'), roles)
        unresolved = {**dated, 'positions': [{'isin': None, 'identity_source': 'unresolved'}]}
        self.assertNotIn(('P01', 'portfolio_fund_weights'), supplied_roles(None, [], portfolio=unresolved))

