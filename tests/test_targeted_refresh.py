"""Targeted source repair must never silently refresh the wrong source."""
from unittest.mock import patch
import unittest

from sqlalchemy import create_engine

from finance_dashboard.worker import refresh_all, main
from finance_dashboard.catalog import load_documents


class TargetedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.series = {row["id"]: row for row in load_documents()[0]["series"]}

    def tearDown(self):
        self.engine.dispose()

    def test_can_refresh_exact_pwt_country_series_without_running_50_other_sources(self):
        ids = {"labour.de.pwt_labour_share",
               "labour.fr.pwt_labour_share",
               "labour.it.pwt_labour_share"}
        attempted = []
        with patch("finance_dashboard.worker.IngestionService") as service:
            service.return_value.refresh.side_effect = lambda sid, **kw: (
                attempted.append((sid,kw["full"])) or {
                    "series_id":sid, "status":"success","received":8})
            count = refresh_all(self.engine,full=True,series_ids=ids)
        self.assertEqual(count,0)
        self.assertEqual(set(sid for sid,_ in attempted),ids)
        self.assertEqual(len(attempted),3)
        self.assertTrue(all(full for _,full in attempted))

    def test_invalid_id_refuses_network_and_fails_loudly(self):
        with patch("finance_dashboard.worker.IngestionService") as service:
            with self.assertRaisesRegex(ValueError,"Unknown series"):
                refresh_all(self.engine,series_ids={"labour.fake.pwt_labour_share"})
            service.assert_not_called()

    def test_cli_accepts_multiple_series_while_staying_macro_only(self):
        ids = ["labour.de.pwt_labour_share","labour.fr.pwt_labour_share"]
        with patch("finance_dashboard.worker.make_engine",return_value=self.engine), \
             patch("finance_dashboard.worker.refresh_all",return_value=0) as refresh:
            code=main(["--once","--macro-only","--full",
                "--series",ids[0],"--series",ids[1]])
        self.assertEqual(code,0)
        self.assertEqual(refresh.call_args.kwargs["series_ids"],set(ids))
        self.assertTrue(refresh.call_args.kwargs["full"])

    def test_cli_rejects_market_only_with_series_selection(self):
        with self.assertRaises(SystemExit) as raised:
            main(["--once","--market-only","--series","labour.de.pwt_labour_share"])
        self.assertEqual(raised.exception.code,2)


if __name__=="__main__":
    unittest.main()
