"""Scientific source-role declarations: a mapped input is never source proof."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APPROVED_IDS = {
    "C01", "C02", "C03", "C05", "C06", "M01", "M02", "M04",
    "F01", "F02", "F03", "F04", "F05", "F06", "F07",
    "V01", "V02", "V03", "V05", "L01", "L02", "L03", "L04", "L05", "L07",
    "G01", "G02", "G03", "G05", "G06", "P01", "P02", "P03", "P04", "P05",
    "P06", "P07",
}


class ComparisonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((ROOT / "definitions/phase2_research_corpus.json").read_text())
        cls.analyses = {row["id"]: row for row in cls.document["analyses"]}
        registry = json.loads((ROOT / "definitions/series.json").read_text())
        cls.series = {row["id"]: row for row in registry["series"]}

    def contract_row(self, analysis_id):
        return self.analyses[analysis_id]

    def contract(self, analysis_id):
        contract = self.analyses[analysis_id].get("comparison_contract")
        self.assertIsInstance(contract, dict, f"{analysis_id}: missing requirement graph")
        return contract

    def requirement(self, analysis_id, role):
        rows = self.contract(analysis_id)["original_requirements"]
        found = [row for row in rows if row["role"] == role]
        self.assertEqual(len(found), 1, (analysis_id, role))
        return found[0]

    def variant(self, analysis_id, variant_id):
        found = [row for row in self.contract(analysis_id)["variants"] if row["id"] == variant_id]
        self.assertEqual(len(found), 1, (analysis_id, variant_id))
        return found[0]

    def test_all_35_have_source_roles_without_editable_evidence_certificates(self):
        self.assertEqual(self.document["schema_version"], 4)
        self.assertEqual(set(self.analyses), APPROVED_IDS)
        for analysis_id, row in self.analyses.items():
            with self.subTest(analysis=analysis_id):
                self.assertNotIn("evidence_status", row)
                self.assertNotIn("coverage", row)
                contract = self.contract(analysis_id)
                self.assertEqual(contract["version"], 1)
                self.assertTrue(contract["specification"].startswith(
                    "docs/PHASE1_ANALYSIS_SPECIFICATIONS.md#"))
                requirements = contract["original_requirements"]
                self.assertTrue(requirements)
                self.assertEqual(len({r["role"] for r in requirements}), len(requirements))
                for requirement in requirements:
                    self.assertTrue(requirement["description"])
                    self.assertIsInstance(requirement["expected"], dict)
                    self.assertIn(requirement["temporal_requirement"], {
                        "current_source_snapshot", "source_asof", "first_publication", "latest_revised"})
                    ids = requirement["series_ids"]
                    self.assertEqual(len(ids), len(set(ids)))
                    self.assertTrue(set(ids).issubset(self.series))
                    self.assertNotIn("requirement_status", requirement)

    def test_mapped_roles_and_variants_preserve_native_frequency_and_units(self):
        for analysis_id in APPROVED_IDS:
            contract = self.contract(analysis_id)
            for requirement in contract["original_requirements"]:
                for sid in requirement["series_ids"]:
                    with self.subTest(analysis=analysis_id, role=requirement["role"], series=sid):
                        self.assertEqual(requirement["expected"]["frequency"], self.series[sid]["frequency"])
                        self.assertEqual(requirement["expected"]["unit"], self.series[sid]["unit"])
                        self.assertIn(self.series[sid]["geography"], requirement["expected"]["geography"])
            for variant in contract["variants"]:
                self.assertEqual(variant["join"], "exact_period_intersection")
                self.assertEqual(variant["missingness"], "no_fill")
                self.assertEqual(variant["temporal_mode"], "current_source_snapshot")
                self.assertEqual(variant["end"], "latest_common")
                self.assertTrue(variant["limitations"])
                self.assertTrue(variant["scope"])
                self.assertTrue(variant["series_ids"])
                for sid in variant["series_ids"]:
                    self.assertIn(sid, self.series)
                    self.assertEqual(self.series[sid]["frequency"], variant["frequency"])
                self.assertTrue(set(variant["checks"]).issubset({
                    "yield_decomposition", "share_partition_100", "tiva_value_added_share"}))

    def test_annual_growth_cannot_satisfy_quarterly_gdp_or_employment_levels(self):
        gdp = self.requirement("C01", "quarterly_real_gdp")
        self.assertEqual(gdp["series_ids"], ["activity.us.real_gdp_level"])
        self.assertEqual(gdp["expected"]["frequency"], "Q")
        employment = self.requirement("C05", "employment_level")
        self.assertEqual(employment["series_ids"], ["activity.us.nonfarm_payrolls"])
        self.assertNotIn("requirement_status", employment)
        self.assertEqual(employment["expected"]["unit"], "thousands_persons")
        self.assertIn("PAYEMS", employment["description"])

    def test_original_income_top1_and_missing_wiid_are_not_replaced_by_wealth(self):
        top1 = self.requirement("L07", "pretax_income_top1")
        self.assertEqual(len(top1["series_ids"]), 6)
        self.assertTrue(all(".pretax_income.top1" in sid for sid in top1["series_ids"]))
        # Survey Gini comes from World Bank PIP survey series, never from wealth or WID shares.
        gini = self.requirement("L07", "wiid_gini")["series_ids"]
        self.assertTrue(gini and all(sid.endswith(".gini_survey_wdi") for sid in gini))
        income = self.variant("L07", "wid_pretax_income_top10_bottom50")
        self.assertEqual(len(income["series_ids"]), 12)
        self.assertTrue(all(".pretax_income." in sid for sid in income["series_ids"]))
        self.assertFalse(income["satisfies_original_method"])
        self.assertEqual(income["start"], "1980-01-01")

    def test_new_activity_policy_and_nominal_gdp_panels_preserve_explicit_scope(self):
        activity = self.variant("C05", "us_monthly_industrial_production_payrolls")
        self.assertEqual(activity["frequency"], "M")
        self.assertEqual(activity["series_ids"], ["activity.us.industrial_production",
                                                 "activity.us.nonfarm_payrolls"])
        self.assertFalse(activity["satisfies_original_method"])
        self.assertNotIn("activity.us.real_gdp_level", activity["series_ids"])
        policy = self.variant("M01", "us_effective_funds_target_corridor")
        self.assertEqual(policy["start"], "2008-12-16")
        self.assertEqual(len(policy["series_ids"]), 3)
        gdp = self.variant("G02", "wdi_current_usd_country_world_gdp")
        self.assertEqual(len(gdp["series_ids"]), 8)
        self.assertEqual(len({self.series[sid]["geography"] for sid in gdp["series_ids"]}), 8)
        self.assertFalse(any(self.series[sid]["geography"] == "EMU" for sid in gdp["series_ids"]))
        income = self.variant("L07", "wid_pretax_income_top1_top10_bottom50")
        self.assertEqual(len(income["series_ids"]), 18)
        self.assertFalse(income["checks"])
        self.assertIn("nested", income["scope"])

    def test_exact_us_productivity_pay_method_keeps_output_and_cpi_deflators_distinct(self):
        exact = self.variant("L01", "us_nonfarm_output_deflated_pay")
        self.assertEqual(set(exact["series_ids"]), {
            "labour.us.nonfarm_productivity", "labour.us.nonfarm_hourly_comp",
            "prices.us.nonfarm_output_deflator"})
        self.assertTrue(exact["satisfies_original_method"])
        for role, source_key in (("us_productivity", "OPHNFB"),
                                 ("us_nominal_hourly_compensation", "COMPNFB"),
                                 ("us_output_deflator", "IPDNBS")):
            requirement = self.requirement("L01", role)
            self.assertEqual(requirement["expected"]["index_base"], "2017=100")
            # Descriptive evidence tier (Phase 1 revision 2026-11-06).
            self.assertEqual(requirement["temporal_requirement"], "latest_revised")
            self.assertEqual(self.series[requirement["series_ids"][0]]["source_key"], source_key)
        cpi = self.variant("L01", "us_nonfarm_cpi_real_compensation")
        self.assertEqual(set(cpi["series_ids"]), {
            "labour.us.nonfarm_productivity", "labour.us.nonfarm_real_compensation_cpi"})
        self.assertFalse(cpi["satisfies_original_method"])

    def test_us_yield_identity_needs_all_three_original_measurements(self):
        variant = self.variant("M02", "us_treasury_10y_decomposition")
        self.assertEqual(set(variant["series_ids"]), {
            "bond.us.nominal_10y", "bond.us.real_10y", "bond.us.breakeven_10y"})
        self.assertEqual(variant["checks"], ["yield_decomposition"])
        self.assertTrue(variant["satisfies_original_method"])

    def test_credit_dsr_panel_pairs_only_the_same_available_countries(self):
        panel = self.variant("F03", "bis_us_jp_credit_gap_private_dsr")
        self.assertEqual(set(panel["series_ids"]), {
            "credit_gap.us.bis", "credit_gap.jp.bis", "debt_service.us.private.bis",
            "debt_service.jp.private.bis"})
        self.assertEqual(panel["frequency"], "Q")
        self.assertFalse(panel["satisfies_original_method"])

    def test_mixed_frequency_questions_keep_native_inputs_in_separate_panels(self):
        monthly = self.variant("C02", "us_monthly_sahm_recession_inputs")
        daily = self.variant("C02", "us_daily_published_yield_spread")
        self.assertEqual(monthly["frequency"], "M")
        self.assertEqual(daily["frequency"], "D")
        self.assertFalse(set(monthly["series_ids"]) & set(daily["series_ids"]))
        inflation = self.variant("C06", "weo_country_growth_inflation_inputs")
        commodity = self.variant("C06", "pink_sheet_monthly_commodity_inputs")
        self.assertEqual(inflation["frequency"], "A")
        self.assertEqual(commodity["frequency"], "M")
        self.assertTrue(inflation["satisfies_original_method"])
        self.assertTrue(commodity["satisfies_original_method"])
        self.assertEqual(len(inflation["series_ids"]), 6)
        self.assertEqual(len(commodity["series_ids"]), 3)

    def test_nonbank_and_q_variants_do_not_invent_missing_components(self):
        nonbank = self.variant("F07", "us_nonbank_native_balance_sheets")
        self.assertEqual(len(nonbank["series_ids"]), 4)
        self.assertFalse(nonbank["checks"])
        self.assertFalse(nonbank["satisfies_original_method"])
        # Equity is Z.1's own published equity-capital line, never assets minus liabilities.
        equity = self.requirement("F07", "meaningful_sector_equity")["series_ids"]
        self.assertEqual(equity, ["funding.us.broker_equity_capital", "funding.us.broker_total_liabilities_equity"])
        self.assertFalse(set(equity) & set(nonbank["series_ids"]))
        self.assertEqual(self.series["funding.us.broker_equity_capital"]["source_key"], "BOGZ1FL665080003Q")
        q = self.variant("V02", "bea_annual_q_definition_panel")
        self.assertEqual(q["frequency"], "A")
        self.assertEqual(len(q["series_ids"]), 3)
        self.assertNotIn("valuation.us.cape", q["series_ids"])
        # Components are BEA's own published Table A/B rows, never back-solved from the Q ratios.
        components = self.requirement("V02", "q_accounting_components")["series_ids"]
        self.assertEqual({self.series[sid]["source_key"] for sid in components},
                         {"BEA_2026_TABLE_B_NFC_PRODUCED_ASSETS", "BEA_2026_TABLE_A_NFC_NET_OPERATING_SURPLUS"})
        self.assertFalse(set(components) & set(q["series_ids"]))

    def test_currency_context_reuses_the_existing_realized_rate_without_fx_substitution(self):
        self.assertEqual(self.requirement("M04", "effective_federal_funds")["series_ids"],
                         ["policy_rate.us.fed_effective"])
        panel = self.variant("M04", "us_effective_funds_ecb_deposit_inputs")
        self.assertEqual(panel["frequency"], "D")
        self.assertFalse(panel["satisfies_original_method"])
        # Phase 1 revision: generic FX quotes became explicit ECB reference-rate roles.
        self.assertIn("exchange_rate_quotes", {item["role"] for item in self.contract_row("M04")["descoped_roles"]})
        self.assertEqual(self.requirement("M04", "usd_per_eur")["series_ids"], ["fx.usd_per_eur.ecb"])
        self.assertEqual(self.requirement("M04", "jpy_per_eur")["series_ids"], ["fx.jpy_per_eur.ecb"])

    def test_global_multiasset_fallback_is_not_bound_as_original_equity_or_bonds(self):
        panel = self.variant("P02", "p02_doeswijk_swinkels_global_multiasset_usd")
        sid = "returns.doeswijk_swinkels.global_multiasset.usd.nominal"
        self.assertEqual(panel["series_ids"], [sid])
        self.assertEqual(panel["kind"], "approved_fallback")
        self.assertEqual(panel["frequency"], "M")
        self.assertEqual(panel["start"], "1970-01-01")
        self.assertFalse(panel["satisfies_original_method"])
        for role in self.contract("P02")["original_requirements"]:
            self.assertNotIn(sid, role["series_ids"])

    def test_p03_context_is_disjoint_from_original_and_bounded_comparisons(self):
        question = self.analyses["P03"]
        contract = question["comparison_contract"]
        bound = {
            sid
            for item in contract["original_requirements"] + contract["variants"]
            for sid in item["series_ids"]
        }
        context = question["context_series_ids"]
        self.assertEqual(len(context), len(set(context)))
        self.assertFalse(set(context) & bound)
        self.assertEqual(set(context), {
            "returns.french.developed.market_excess_usd",
            "returns.french.emerging.market_excess_usd",
            "returns.swinkels.us.sovereign_10y_modelled_local",
            "returns.swinkels.us.sovereign_10y_original_1962_usd",
        })
        for region in ("developed", "emerging"):
            variant = self.variant("P03", f"p03_french_{region}_us_recession_context")
            self.assertIn(f"returns.french.{region}.market_total_usd", variant["series_ids"])
            self.assertIn(f"returns.french.{region}.risk_free_usd", variant["series_ids"])
            self.assertNotIn(f"returns.french.{region}.market_excess_usd", variant["series_ids"])
            self.assertFalse(variant["satisfies_original_method"])

    def test_p03_academic_recession_fallbacks_keep_native_units_and_hindsight_limits(self):
        original = self.contract("P03")["original_requirements"]
        self.assertEqual(
            next(role for role in original if role["role"] == "investment_total_return")["series_ids"],
            ["equity.world.msci_acwi_netr_usd"])
        # The USD one-month T-bill return is the matching-currency risk-free benchmark.
        self.assertEqual(
            next(role for role in original if role["role"] == "benchmark_risk_free")["series_ids"],
            ["returns.french.developed.risk_free_usd"])
        self.assertEqual(
            next(role for role in original if role["role"] == "market_shock_dates")["series_ids"], [])
        for region, since in (("developed", "1990-07-01"), ("emerging", "1989-07-01")):
            variant = self.variant("P03", f"p03_french_{region}_us_recession_context")
            ids = [f"returns.french.{region}.market_total_usd",
                   f"returns.french.{region}.risk_free_usd",
                   "recession.us.nber_indicator"]
            self.assertEqual(variant["series_ids"], ids)
            self.assertEqual(variant["kind"], "approved_fallback")
            self.assertFalse(variant["satisfies_original_method"])
            self.assertEqual(variant["frequency"], "M")
            self.assertEqual(variant["start"], since)
            self.assertEqual(variant["join"], "exact_period_intersection")
            self.assertEqual(variant["missingness"], "no_fill")
            self.assertEqual(variant["temporal_mode"], "current_source_snapshot")
            for sid in ids[:2]:
                self.assertEqual(self.series[sid]["provider"], "FRENCH_RETURNS")
                self.assertEqual(self.series[sid]["unit"], "percent")
                self.assertEqual(self.series[sid]["frequency"], "M")
                self.assertEqual(self.series[sid]["currency"], "USD")
            self.assertEqual(self.series[ids[2]]["source_key"], "USREC")
            self.assertEqual(self.series[ids[2]]["unit"], "index")
            limitations = " ".join(variant["limitations"]).lower()
            self.assertIn("retrospective", limitations)
            self.assertIn("first-publication", limitations)
            self.assertIn("does not compute portfolio drawdowns", limitations)

    def test_property_panel_and_dsr_baseline_do_not_invent_frequency_or_coverage(self):
        property_panel = self.variant("F06", "us_property_credit_dsr")
        self.assertEqual(property_panel["start"], "1999-01-01")
        self.assertEqual(set(property_panel["series_ids"]), {
            "property.us.real_residential.bis", "property.us.commercial_all.bis",
            "credit_gap.us.bis", "debt_service.us.private.bis"})
        annual_commercial = self.requirement("F06", "commercial_property_portugal")
        self.assertEqual(annual_commercial["expected"]["frequency"], "A")
        dsr = self.variant("F02", "bis_dsr_country_sector_panel")
        self.assertEqual(len(dsr["series_ids"]), 8)
        self.assertEqual(dsr["baseline_window"], {"start": "2000-01-01", "end": "2007-10-01"})
        self.assertFalse(dsr["satisfies_original_method"])

    def test_net_worth_partition_does_not_claim_financial_asset_composition(self):
        variant = self.variant("L05", "us_dfa_four_net_worth_shares")
        self.assertEqual(len(variant["series_ids"]), 4)
        self.assertEqual(variant["checks"], ["share_partition_100"])
        self.assertFalse(variant["satisfies_original_method"])
        # Composition comes from separate DFA holdings levels, never from the net-worth share partition.
        components = self.requirement("L05", "financial_asset_components")["series_ids"]
        self.assertEqual(components, [f"wealth.us.{g}.equities_mutual_funds"
                                      for g in ("top1", "next9", "middle40", "bottom50")])
        self.assertFalse(set(components) & set(variant["series_ids"]))
        self.assertEqual(self.requirement("L05", "net_worth_top_point1")["series_ids"], ["wealth.us.top_point1_share"])

    def test_tiva_alternative_does_not_satisfy_missing_icio_matrices(self):
        for role in ("intermediate_transactions", "gross_output", "final_demand", "industry_value_added"):
            self.assertEqual(self.requirement("G06", role)["series_ids"], [])
        variant = self.variant("G06", "tiva_foreign_final_demand_country_panel")
        self.assertEqual(len(variant["series_ids"]), 21)
        self.assertEqual(variant["checks"], ["tiva_value_added_share"])
        self.assertFalse(variant["satisfies_original_method"])

    def test_external_credit_stock_and_niip_are_native_sources_not_gap_proxies(self):
        # Original G05 roles now have five concrete country series each.
        # Registrations prove source identity, not acquisition or publication vintage.
        countries = (("us", "US", "USA"), ("jp", "JP", "JPN"),
                     ("de", "DE", "DEU"), ("cn", "CN", "CHN"),
                     ("pt", "PT", "PRT"))
        credit = self.requirement("G05", "private_credit_outstanding")
        niip = self.requirement("G05", "net_international_investment_position")
        self.assertEqual(credit["series_ids"], [
            f"credit.{code}.private_nonfinancial_stock_bis" for code, _, _ in countries
        ])
        self.assertEqual(niip["series_ids"], [
            f"external.{code}.imf_iip_net_position_usd" for code, _, _ in countries
        ])
        self.assertEqual(credit["expected"]["frequency"], "Q")
        self.assertEqual(credit["expected"]["unit"], "billion_local_currency")
        self.assertEqual(niip["expected"]["frequency"], "A")
        self.assertEqual(niip["expected"]["unit"], "usd")
        self.assertEqual(credit["temporal_requirement"], "latest_revised")
        self.assertEqual(niip["temporal_requirement"], "latest_revised")
        for (code, bis_country, imf_country), stock_id, niip_id in zip(
                countries, credit["series_ids"], niip["series_ids"], strict=True):
            with self.subTest(country=code):
                stock = self.series[stock_id]
                position = self.series[niip_id]
                self.assertEqual(stock["provider"], "BIS_TOTAL_CREDIT")
                self.assertIn(f"/Q.{bis_country}.P.A.M.XDC.A", stock["source_key"])
                self.assertEqual(stock["geography"], bis_country)
                self.assertEqual(stock["unit"], "billion_local_currency")
                self.assertEqual(stock["frequency"], "Q")
                self.assertNotIn("gap", stock_id)
                self.assertEqual(position["provider"], "IMF_BOP_IIP")
                self.assertIn(f"/{imf_country}..NIIP.USD.A", position["source_key"])
                self.assertEqual(position["geography"], imf_country)
                self.assertEqual(position["unit"], "usd")
                self.assertEqual(position["frequency"], "A")

        # The older bounded WEO/WDI annual panel remains a narrower comparison.
        # It never substitutes the global credit gap or certifies G05's full method.
        narrower = self.variant("G05", "weo_current_account_ratio_wdi_nominal_gdp")
        self.assertFalse(set(narrower["series_ids"]) & set(credit["series_ids"]))
        self.assertFalse(set(narrower["series_ids"]) & set(niip["series_ids"]))
        self.assertFalse(narrower["satisfies_original_method"])
        self.assertEqual(narrower["kind"], "approved_narrower")
        self.assertEqual(narrower["temporal_mode"], "current_source_snapshot")
        for analysis_id in APPROVED_IDS:
            contract = self.contract(analysis_id)
            for variant in contract["variants"]:
                self.assertNotIn("evidence_status", variant)
                self.assertNotIn("coverage", variant)
                self.assertNotIn("fully_validated", variant)
                if variant["satisfies_original_method"]:
                    self.assertEqual(variant["kind"], "original_scope")


if __name__ == "__main__":
    unittest.main()
