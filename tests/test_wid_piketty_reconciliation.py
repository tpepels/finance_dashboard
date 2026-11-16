"""Reconcile new Piketty WID scalar originals independently of ingestion."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import io
import unittest

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.source_original_gate import verified_original_history
from finance_dashboard.source_reconciliation import (
    SOURCE_IDS, _reconcile_values, _wid_source,
)
from finance_dashboard.wid import WidClient, parse_piketty_original
from test_wid_piketty import extended_pair


class PikettyOriginalReconciliationTests(unittest.TestCase):
    def test_originals_are_checked_by_same_sha_verified_wid_pair_and_current_catalog(self):
        data,metadata=extended_pair()
        hits=[]
        def response(request):
            hits.append(str(request.url))
            return httpx.Response(200,text=metadata if "metadata" in request.url.path else data)
        with TemporaryDirectory() as folder, httpx.Client(
                transport=httpx.MockTransport(response)) as client:
            root=Path(folder)
            WidClient(client,archive_dir=root).fetch("inequality.us.pretax_income.top10")
            self.assertEqual(len(hits),2)
            values,evidence=_wid_source(root,"US")
            sid="piketty.us.real_pretax_average.all"
            self.assertIn(sid,SOURCE_IDS)
            self.assertEqual(values[sid][date(2024,1,1)],Decimal("110"))
            self.assertEqual(values["piketty.us.wealth_to_income.national"][date(2024,1,1)],
                             Decimal("6"))
            self.assertEqual(values["inequality.us.pretax_income.top10"][date(2024,1,1)],
                             Decimal(".46"))
            self.assertTrue(evidence["source_sha256"])
            accepted=_reconcile_values({sid:{date(2024,1,1):Decimal("110")}},"sqlite",root)
            self.assertTrue(accepted["all_stored_histories_reconciled"])
            row=accepted["series"][0]
            declaration=next(x for x in load_documents()[0]["series"] if x["id"]==sid)
            self.assertTrue(verified_original_history(row,declaration,1))
            self.assertEqual(len(hits),2)

            # The original country file genuinely lacks this other registered
            # WID measure. It must be unavailable, not a matched empty proof.
            absent=_reconcile_values({
                "piketty.us.net_national_wealth":{date(2024,1,1):Decimal("550")}
            },"sqlite",root)
            item=absent["series"][0]
            self.assertEqual(item["failure_code"],"source_empty")
            self.assertFalse(item["source_values_match"])
            self.assertIsNone(item["source_sha256"])

    def test_unrelated_optional_metadata_conflict_does_not_poison_valid_source(self):
        data,metadata=extended_pair()
        reader=csv.DictReader(io.StringIO(metadata),delimiter=";")
        fields=list(reader.fieldnames)
        rows=list(reader)
        rows.append(next(x for x in rows if x["variable"]=="aptinc992j").copy())
        output=io.StringIO()
        writer=csv.DictWriter(output,fieldnames=fields,delimiter=";",lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        parsed=parse_piketty_original(data,output.getvalue(),area="US",strict=False)
        self.assertEqual(parsed[("aptinc992j","p0p100")],{})
        self.assertEqual(parsed[("wnweal999i","p0p100")][date(2024,1,1)],
                         Decimal("6"))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            parse_piketty_original(data,output.getvalue(),area="US")

    def test_tampered_original_bytes_withhold_new_source(self):
        data,metadata=extended_pair()
        def respond(request):
            return httpx.Response(200,text=metadata if "metadata" in request.url.path else data)
        with TemporaryDirectory() as folder, httpx.Client(
                transport=httpx.MockTransport(respond)) as client:
            root=Path(folder)
            WidClient(client,archive_dir=root).fetch("inequality.us.pretax_income.top10")
            original=next(root.glob("wid/US/*/WID_data_US.csv"))
            original.write_text(original.read_text()+"\nmalicious record")
            report=_reconcile_values({
                "piketty.us.real_pretax_average.all":{date(2024,1,1):Decimal("110")}
            },"sqlite",root)
            self.assertFalse(report["all_stored_histories_reconciled"])
            self.assertEqual(report["series"][0]["failure_code"],"source_hash_mismatch")


if __name__=="__main__":
    unittest.main()
