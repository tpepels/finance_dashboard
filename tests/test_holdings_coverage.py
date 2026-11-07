"""Value-weighted field coverage of original fund holdings."""
import unittest

from finance_dashboard.holdings_coverage import sec_coverage, ucits_coverage


class HoldingsCoverageTests(unittest.TestCase):
    def test_sec_rows_weight_by_value_and_skip_derivatives(self):
        positions = [
            {"value_usd": "900", "cusip": "037833100", "security_identifiers": [], "lei": "HWUPKR0MPOU8FGXBT394",
             "name": "Apple Inc", "issuer_country": "US", "is_derivative": False},
            {"value_usd": "100", "cusip": "N/A", "security_identifiers": [{"type": "isin", "value": "CNE000000M72"}],
             "lei": "N/A", "name": "Wingtech", "issuer_country": "CN", "is_derivative": False},
            {"value_usd": "-50", "cusip": "N/A", "security_identifiers": [], "lei": "N/A",
             "name": "Future", "issuer_country": "US", "is_derivative": True},
        ]
        coverage = sec_coverage(positions)
        self.assertEqual(coverage["security_positions"], 2)
        self.assertEqual(coverage["fields"]["security_identifier"], "1.000000")
        self.assertEqual(coverage["fields"]["issuer_identifier"], "0.900000")
        self.assertEqual(coverage["fields"]["sector"], "0.000000")

    def test_ucits_rows_exclude_cash_and_count_only_reported_fields(self):
        positions = [
            {"asset_class": "Equity", "market_value": "8,000", "name": "APPLE", "isin": None,
             "reported_location": "United States", "sector": "Information Technology"},
            {"asset_class": "Equity", "market_value": "2,000", "name": "SAP", "isin": None,
             "reported_location": "Germany", "sector": "-"},
            {"asset_class": "Cash", "market_value": "500", "name": "USD CASH", "reported_location": "United States"},
        ]
        coverage = ucits_coverage(positions)
        self.assertEqual(coverage["security_positions"], 2)
        self.assertEqual(coverage["fields"]["country"], "1.000000")
        self.assertEqual(coverage["fields"]["sector"], "0.800000")
        self.assertEqual(coverage["fields"]["security_identifier"], "0.000000")


if __name__ == "__main__":
    unittest.main()
