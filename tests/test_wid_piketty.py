"""WID Piketty source-key identity, optional original verification and pair reuse."""
from datetime import date
from decimal import Decimal
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.bis import ProviderError
from finance_dashboard.wid import (
    WID_SERIES, WID_ALL_SERIES, WID_PIKETTY_SERIES, WidClient,
    parse_piketty_original,
)
from test_wid import fixtures


def extended_pair():
    data, metadata = fixtures("US")
    def append(text, records):
        input_rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        keys = list(input_rows[0])
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=keys, delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerows(input_rows)
        for item in records:
            writer.writerow({key: item.get(key, "") for key in keys})
        return output.getvalue()
    data = append(data, [
        {"country":"US","variable":"shweal992j","percentile":"p99p100",
         "year":"2024","value":".30","age":"992","pop":"j"},
        {"country":"US","variable":"aptinc992j","percentile":"p0p100",
         "year":"2024","value":"110","age":"992","pop":"j"},
        {"country":"US","variable":"aptinc992j","percentile":"p0p50",
         "year":"2024","value":"65","age":"992","pop":"j"},
        {"country":"US","variable":"wwealn999i","percentile":"p0p100",
         "year":"2024","value":"6","age":"999","pop":"i"},
        {"country":"US","variable":"mnninc999i","percentile":"p0p100",
         "year":"2024","value":"110","age":"999","pop":"i"},
    ])
    metadata = append(metadata, [
        {"country":"US","variable":"aptinc992j","age":"992","pop":"j","unit":"USD",
         "source":"WID original","method":"WID distribution methodology"},
        {"country":"US","variable":"wwealn999i","age":"999","pop":"i","unit":"ratio",
         "source":"WID original","method":"WID national accounts methodology"},
        {"country":"US","variable":"mnninc999i","age":"999","pop":"i","unit":"USD",
         "source":"WID original","method":"WID real national income methodology"},
    ])
    return data, metadata


class WidPikettyOriginalTests(unittest.TestCase):
    def test_exact_registered_codes_preserve_base_sources_and_world_identity(self):
        self.assertEqual(len(WID_SERIES),30)
        self.assertEqual(len(WID_PIKETTY_SERIES),90)
        self.assertEqual(len(WID_ALL_SERIES),120)
        self.assertEqual(WID_ALL_SERIES["piketty.us.wealth_to_income.national"],
                         ("US","wwealn999i","p0p100"))
        self.assertEqual(WID_ALL_SERIES["piketty.world.real_pretax_average.all"],
                         ("WO","aptincj992","p0p100"))
        self.assertEqual(WID_ALL_SERIES["inequality.us.net_personal_wealth.top1"],
                         ("US","shweal992j","p99p100"))

    def test_source_identity_and_population_validation_retains_absent_originals(self):
        data,metadata=extended_pair()
        parsed=parse_piketty_original(data,metadata,area="US")
        self.assertEqual(parsed[("aptinc992j","p0p100")][date(2024,1,1)],Decimal("110"))
        self.assertEqual(parsed[("wwealn999i","p0p100")][date(2024,1,1)],Decimal("6"))
        self.assertEqual(parsed[("shweal992j","p99p100")][date(2024,1,1)],Decimal(".30"))
        self.assertEqual(parsed[("mnweal999i","p0p100")],{})
        self.assertEqual(parsed[("aptinc992j","p90p100")],{})

    def test_invalid_macro_population_and_missing_metadata_are_rejected(self):
        data,metadata=extended_pair()
        invalid=data.replace("wwealn999i;p0p100;2024;6;999;i",
                             "wwealn999i;p0p100;2024;6;992;j")
        self.assertNotEqual(data,invalid)
        with self.assertRaisesRegex(ProviderError,"population mismatch"):
            parse_piketty_original(invalid,metadata,area="US")
        metadata=metadata.replace("WID distribution methodology","")
        with self.assertRaisesRegex(ProviderError,"original method mismatch"):
            parse_piketty_original(data,metadata,area="US")

    def test_same_governed_data_metadata_pair_serves_base_and_new_research_sources(self):
        data,metadata=extended_pair()
        calls=[]
        def respond(request):
            calls.append(str(request.url))
            if "WID_metadata_US.csv" in request.url.path:
                return httpx.Response(200,text=metadata)
            return httpx.Response(200,text=data)
        with TemporaryDirectory() as temp, httpx.Client(
                transport=httpx.MockTransport(respond)) as client:
            root=Path(temp)
            wid=WidClient(client,archive_dir=root)
            original=wid.fetch("inequality.us.pretax_income.top10")
            wealth=wid.fetch("inequality.us.net_personal_wealth.top1")
            annual=wid.fetch("piketty.us.real_pretax_average.all")
            ratio=wid.fetch("piketty.us.wealth_to_income.national")
            self.assertEqual(len(calls),2)
            self.assertEqual(original.observations[date(2024,1,1)], Decimal(".46"))
            self.assertEqual(wealth.observations[date(2024,1,1)],Decimal(".30"))
            self.assertEqual(annual.observations[date(2024,1,1)],Decimal("110"))
            self.assertEqual(ratio.observations[date(2024,1,1)],Decimal("6"))
            self.assertEqual(len(list(root.glob("wid/US/*/manifest.json"))),1)
            with self.assertRaisesRegex(ProviderError,"no matched observations"):
                wid.fetch("piketty.us.net_national_wealth")


if __name__=="__main__":
    unittest.main()
