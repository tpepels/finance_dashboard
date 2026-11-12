"""ODCE country accounts share canonical originals and respect publisher quotas."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from collections import Counter
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base, IngestionRun
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_policy import SourcePolicyGate, managed_client
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.worker import refresh_all
from finance_dashboard.provider_adapters import OECD_NFC_TRANSACTIONS


def country_csv(country: str, stock: bool, *, value: int = 100) -> str:
    header = "REF_AREA,SECTOR,ACCOUNTING_ENTRY,TRANSACTION,INSTR_ASSET,UNIT_MULT,TIME_PERIOD,OBS_VALUE\n"
    if stock:
        return header + f"{country},S11,A,_Z,N11N,6,2024,{value}\n"
    return header + "".join(
        f"{country},S11,{entry},{code},_Z,6,2024,{value+index}\n"
        for index, (code, entry) in enumerate(OECD_NFC_TRANSACTIONS.items())
    )


class RefreshFairnessTests(unittest.TestCase):
    @staticmethod
    def definitions():
        return {row["id"]: row for row in load_documents()[0]["series"]
                if row["provider"] == "OECD_NFC_ACCOUNTS"}

    def test_one_country_original_is_reused_across_six_indicators(self):
        definitions = self.definitions()
        selected = sorted(definitions)[:21]
        requested = []
        def respond(request):
            parts = request.url.path.rsplit("/", 1)[-1].split(".")
            country = parts[1]
            stock = "DF_TABLE9B" in request.url.path
            requested.append((country, stock))
            self.assertEqual(dict(request.url.params), {"format": "csvfile"})
            if not stock:
                self.assertEqual(set(parts[5].split("+")), set(OECD_NFC_TRANSACTIONS))
                self.assertEqual(set(parts[4].split("+")), {"C", "D"})
            return httpx.Response(200, text=country_csv(country, stock))
        with TemporaryDirectory() as temp:
            root = Path(temp)
            engine = create_engine("sqlite+pysqlite:///" + str(root / "observations.sqlite"))
            Base.metadata.create_all(engine)
            now = [1_794_384_000.0]
            gate = SourcePolicyGate(
                state_path=root / "policy.sqlite",
                clock=lambda: now[0],
                sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
            )
            with patch.dict("os.environ", {
                    "FINANCE_SOURCE_POLICY_ACKNOWLEDGED": "oecd-sdmx",
                    "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence")}), \
                 managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http, \
                 patch("finance_dashboard.worker.ProviderRouter",
                       side_effect=lambda: ProviderRouter(http)), \
                 patch("finance_dashboard.worker.record_event"):
                try:
                    self.assertEqual(refresh_all(engine, providers={"OECD_NFC_ACCOUNTS"},
                                                 series_ids=set(selected)), 0)
                    groups = {(definitions[sid]["source_key"].split("/")[0],
                               definitions[sid]["source_key"].endswith("/N11N"))
                              for sid in selected}
                    self.assertEqual(set(requested), groups)
                    self.assertEqual(len(requested), len(groups))
                    self.assertLess(len(requested), len(selected))
                    self.assertLessEqual(len(requested), 20)
                    with Session(engine) as session:
                        self.assertEqual(session.scalar(
                            select(func.count()).select_from(IngestionRun)), len(selected))
                        self.assertEqual(session.scalar(
                            select(func.count()).select_from(IngestionRun)
                            .where(IngestionRun.status == "success")), len(selected))
                finally:
                    engine.dispose()

    def test_low_quota_rotates_to_unserved_countries_without_starvation(self):
        definitions = self.definitions()
        selected = sorted(definitions)[:21]
        now = [1_794_384_000.0]
        calls = []
        cycle = [0]
        def respond(request):
            parts = request.url.path.rsplit("/", 1)[-1].split(".")
            country = parts[1]
            stock = "DF_TABLE9B" in request.url.path
            calls.append((cycle[0], country, stock, now[0]))
            return httpx.Response(200, text=country_csv(country, stock, value=100+cycle[0]))
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.sqlite"
            engine = create_engine("sqlite+pysqlite:///" + str(db))
            Base.metadata.create_all(engine)
            registry = PolicyRegistry()
            registry.by_id["oecd-sdmx"].rate["limit"] = 2
            gate = SourcePolicyGate(
                registry=registry, state_path=root / "policy.sqlite",
                clock=lambda: now[0],
                sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
            )
            with patch.dict("os.environ", {
                    "FINANCE_SOURCE_POLICY_ACKNOWLEDGED": "oecd-sdmx",
                    "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence")}), \
                 managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http, \
                 patch("finance_dashboard.worker.ProviderRouter",
                       side_effect=lambda: ProviderRouter(http)), \
                 patch("finance_dashboard.worker.record_event"), \
                 patch("finance_dashboard.service.now_utc",
                       side_effect=lambda: datetime.fromtimestamp(now[0], timezone.utc)):
                try:
                    for day in range(12):
                        cycle[0] = day
                        refresh_all(engine, providers={"OECD_NFC_ACCOUNTS"},
                                    series_ids=set(selected))
                        self.assertLessEqual(sum(c == day for c, *_ in calls), 2)
                        now[0] += 86400
                        with Session(engine) as session:
                            completed = session.scalar(
                                select(func.count(func.distinct(IngestionRun.series_id)))
                                .where(IngestionRun.status == "success"))
                        if completed == len(selected):
                            break
                    self.assertEqual(completed, len(selected))
                    self.assertTrue(all(
                        sum(start - 3600 < when <= start
                            for _, _, _, when in calls) <= 2
                        for *_, start in calls))
                    # A source that initially hits quota has to move ahead of
                    # already attempted sources in a later cycle.
                    self.assertGreater(len({d for d, *_ in calls}), 1)
                finally:
                    engine.dispose()


if __name__ == "__main__":
    unittest.main()
