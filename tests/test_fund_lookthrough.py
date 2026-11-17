"""Issuer holdings look-through for the owner's equity ETFs.

Excerpts are copied from the issuers' files retrieved on 2026-11-17
(holdings dated 2026-11-16, Vanguard 2026-10-31). They are too short to add
up to 100%, so parser tests capture the rows before the weight check; the
check itself is tested separately.
"""
from datetime import date
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from finance_dashboard import fund_lookthrough as F
from test_captured_source_families import xlsx_from_factual_cells

ISHARES = """<?xml version="1.0"?>
<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<ss:Worksheet ss:Name="Fund Header"><ss:Table><ss:Row><ss:Cell><ss:Data ss:Type="String">iShares MSCI Global Semiconductors UCITS ETF</ss:Data></ss:Cell></ss:Row></ss:Table></ss:Worksheet>
<ss:Worksheet ss:Name="Key Facts"><ss:Table>
<ss:Row><ss:Cell><ss:Data ss:Type="String">Base Currency</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type="String">USD</ss:Data></ss:Cell></ss:Row>
<ss:Row><ss:Cell><ss:Data ss:Type="String">ISIN</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type="String">IE000I8KRLL9</ss:Data></ss:Cell></ss:Row>
</ss:Table></ss:Worksheet>
<ss:Worksheet ss:Name="Holdings"><ss:Table>
<ss:Row><ss:Cell><ss:Data ss:Type="String">All</ss:Data></ss:Cell></ss:Row>
<ss:Row><ss:Cell><ss:Data ss:Type="String">as of</ss:Data></ss:Cell><ss:Cell><ss:Data ss:Type="String">16/Nov/2026</ss:Data></ss:Cell></ss:Row>
<ss:Row>""" + "".join(f'<ss:Cell><ss:Data ss:Type="String">{name}</ss:Data></ss:Cell>' for name in (
    "Issuer Ticker", "Name", "Sector", "Asset Class", "Market Value", "Weight (%)",
    "Notional Value", "Nominal", "Market Currency")) + """</ss:Row>
<ss:Row>""" + "".join(f'<ss:Cell><ss:Data ss:Type="String">{v}</ss:Data></ss:Cell>' for v in (
    "AMD", "ADVANCED MICRO DEVICES", "Information Technology", "Equity", "USD 546,506,894.36",
    "9.83", "546,506,894.36", "1,083,737.00", "USD")) + """</ss:Row>
<ss:Row>""" + "".join(f'<ss:Cell><ss:Data ss:Type="String">{v}</ss:Data></ss:Cell>' for v in (
    "ASML", "ASML HOLDING", "Information Technology", "Equity", "USD 248,472,425.63",
    "4.47", "248,472,425.63", "172,785.00", "EUR")) + """</ss:Row>
</ss:Table></ss:Worksheet></ss:Workbook>"""

SPDR = [["Fund Name:", "State Street® SPDR® MSCI EM Asia UCITS ETF"], ["ISIN:", "IE00B466KX20"],
        ["Ticker Symbol:", "SPYA GY"], ["Holdings As Of:", "16-Nov-2026"], [],
        ["ISIN", "SEDOL", "Security Name", "Currency", "Number of Shares", "Percent of Fund", "Trade Country Name"],
        ["TW0002330008", "6889106", "Taiwan Semiconductor Manufacturing Co. Ltd.", "TWD", 3892865.0, 18.622808, "Taiwan"],
        ["KR7005930003", "6771720", "Samsung Electronics Co. Ltd.", "KRW", 738700.0, 7.742033, "South Korea"],
        ["Unassigned", "Unassigned", "U.S. Dollar", "USD", 90823.0, "-", "United States"],
        [], ["Marketing communication"]]

VANECK = [["All Holdings  11/16/2026"], [],
          ["Number", "Holding Name", "Ticker", "ISIN", "Shares", "Market Value", "% of Net Assets"],
          [1.0, "Rocket Lab Corp", "RKLB US", "US7731211089", "2,156,576", "$ 132,694,121.00", "8.76%"],
          [14.0, "Ses Sa", "SESG FP", "LU0088087324", "11,116,413", "$ 55,921,307.00", "3.69%"]]
VANECK_PAGE = b"<html>VanEck Space Innovators UCITS ETF IE000YU9K6K2</html>"

VANGUARD_FUNDS = json.dumps({"data": {"funds": [{"portId": "9677", "profile": {
    "portId": "9677", "fundFullName": "Vanguard FTSE All-World High Dividend Yield UCITS ETF (USD) Accumulating",
    "identifiers": [{"altIdValue": "IE00BK5BR626"}]}}]}}).encode()
VANGUARD_PAGE = json.dumps({"data": {"borHoldings": [{"holdings": {"totalHoldings": 2, "lastItemKey": None, "items": [
    {"issuerName": "JPMorgan Chase & Co", "marketValuePercentage": 2.01374, "securityType": "EQ.STOCK",
     "effectiveDate": "2026-10-31", "bloombergIsoCountry": "US"},
    {"issuerName": "ASML Holding NV", "marketValuePercentage": 1.2, "securityType": "EQ.STOCK",
     "effectiveDate": "2026-10-31", "bloombergIsoCountry": "NL"}]}}]}}).encode()


def captured(parser, *args):
    seen = {}
    def capture(isin, issuer, as_of, rows, method):
        seen.update(isin=isin, issuer=issuer, as_of=as_of, rows=rows, method=method)
        return seen
    with patch.object(F, "_summary", side_effect=capture):
        parser(*args)
    return seen


class ParserTests(unittest.TestCase):
    def test_ishares_reads_currency_and_checks_the_isin(self):
        seen = captured(F.parse_ishares, ISHARES.encode(), "IE000I8KRLL9")
        self.assertEqual(seen["as_of"], date(2026, 11, 16))
        self.assertEqual(seen["rows"], [(Decimal("9.83"), False), (Decimal("4.47"), True)])
        with self.assertRaises(F.LookthroughError):
            F.parse_ishares(ISHARES.encode(), "IE00B5BMR087")

    def test_spdr_skips_cash_lines_and_stops_at_the_disclaimer(self):
        seen = captured(F.parse_spdr, xlsx_from_factual_cells(SPDR, "holdings"), "IE00B466KX20")
        self.assertEqual(seen["rows"], [(Decimal("18.622808"), False), (Decimal("7.742033"), False)])
        with self.assertRaises(F.LookthroughError):
            F.parse_spdr(xlsx_from_factual_cells(SPDR, "holdings"), "IE00BK5BQT80")

    def test_vaneck_uses_the_exchange_and_the_fund_page_isin(self):
        original = xlsx_from_factual_cells(VANECK, "JEDI_asof_20261116")
        seen = captured(F.parse_vaneck, original, "IE000YU9K6K2", VANECK_PAGE)
        self.assertEqual(seen["rows"], [(Decimal("8.76"), False), (Decimal("3.69"), True)])
        with self.assertRaises(F.LookthroughError):
            F.parse_vaneck(original, "IE0007Y8Y157", VANECK_PAGE)
        unknown = [row[:] for row in VANECK]
        unknown[4][2] = "SESG XX"
        with self.assertRaises(F.LookthroughError):
            captured(F.parse_vaneck, xlsx_from_factual_cells(unknown, "JEDI"), "IE000YU9K6K2", VANECK_PAGE)

    def test_vanguard_needs_the_isin_and_every_holding(self):
        seen = captured(F.parse_vanguard, VANGUARD_FUNDS, [VANGUARD_PAGE], "IE00BK5BR626", "9677")
        self.assertEqual(seen["rows"], [(Decimal("2.01374"), False), (Decimal("1.2"), True)])
        with self.assertRaises(F.LookthroughError):
            F.parse_vanguard(VANGUARD_FUNDS, [VANGUARD_PAGE], "IE00BFMXXD54", "9677")
        short = VANGUARD_PAGE.replace(b'"totalHoldings": 2', b'"totalHoldings": 3')
        with self.assertRaises(F.LookthroughError):
            captured(F.parse_vanguard, VANGUARD_FUNDS, [short], "IE00BK5BR626", "9677")


class ArithmeticTests(unittest.TestCase):
    def test_summary_requires_weights_near_100_percent(self):
        summary = F._summary("X", "test", date(2026, 11, 16),
                             [(Decimal("60"), False), (Decimal("40"), True)], "m")
        self.assertEqual(summary["euro_share"], "0.4000")
        with self.assertRaises(F.LookthroughError):
            F._summary("X", "test", date(2026, 11, 16), [(Decimal("60"), True)], "m")

    def test_portfolio_share_is_value_weighted_over_equity_funds_only(self):
        holdings = {"as_of": "2026-11-11", "summary": {"funds": [
            {"isin": "A", "name": "a", "value_eur": 300.0, "asset_class": "equity"},
            {"isin": "B", "name": "b", "value_eur": 100.0, "asset_class": "equity"},
            {"isin": "G", "name": "gold", "value_eur": 50.0, "asset_class": "precious_metals"}]}}
        funds = {isin: {"issuer": "t", "holdings_date": "2026-11-16", "holdings": 1,
                        "euro_share": share, "euro_method": "m"} for isin, share in (("A", "0.1"), ("B", "0.5"))}
        result = F.portfolio_euro_share(holdings, funds)
        self.assertEqual(result["equity_euro_share"], 0.2)
        with self.assertRaises(F.LookthroughError):
            F.portfolio_euro_share(holdings, {"A": funds["A"]})

    def test_every_owner_fund_has_a_registered_issuer_source(self):
        self.assertEqual(len(F.FUNDS), 11)
        self.assertEqual({source.issuer for source in F.FUNDS.values()},
                         {"ishares", "spdr", "vaneck", "vanguard"})


class ArchiveFallbackTests(unittest.TestCase):
    def test_archived_originals_are_reparsed_and_tampering_is_rejected(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        source = F.FUNDS["IE000YU9K6K2"]
        original = xlsx_from_factual_cells(VANECK, "JEDI_asof_20261116")
        def fake_summary(isin, issuer, as_of, rows, method):
            return {"isin": isin, "issuer": issuer, "holdings_date": as_of.isoformat(),
                    "holdings": len(rows), "euro_share": "0.3", "euro_method": method}
        with TemporaryDirectory() as tmp, patch.object(F, "_summary", side_effect=fake_summary):
            root = Path(tmp)
            summary = F.parse_vaneck(original, source.isin, VANECK_PAGE)
            bundle = F.archive_fund(root, summary, {"response-0.bin": VANECK_PAGE,
                                                    "response-1.bin": original}, ["a", "b"])
            found = F.latest_archived(root, source, today=date(2026, 11, 17))
            self.assertTrue(found["from_archive"])
            self.assertEqual(found["holdings_date"], "2026-11-16")
            self.assertIsNone(F.latest_archived(root, source, today=date(2027, 1, 31)))
            (bundle / "response-1.bin").write_bytes(original + b"x")
            self.assertIsNone(F.latest_archived(root, source, today=date(2026, 11, 17)))


if __name__ == "__main__":
    unittest.main()
