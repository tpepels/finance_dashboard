"""A publisher's daily quota must not permanently starve later catalogue IDs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base, IngestionRun
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_policy import SourcePolicyGate, managed_client
from finance_dashboard.worker import refresh_all


class RefreshFairnessTests(unittest.TestCase):
    def test_permanent_parsing_failures_cannot_starve_a_valid_source_or_its_later_refresh(self):
        from datetime import datetime, timezone
        definitions = {r['id']: r for r in load_documents()[0]['series']
                       if r['provider'] == 'OECD_NFC_ACCOUNTS'}
        selected = sorted(definitions)[:21]
        lookup = {definitions[sid]['source_key']: sid for sid in selected}
        now = [1_794_384_000.0]
        calls = []
        cycle = [0]
        def respond(request):
            dims = request.url.path.rsplit('/', 1)[-1].split('.')
            stock = 'DF_TABLE9B' in request.url.path
            country, entry = dims[1], dims[4]
            transaction = dims[6] if stock else dims[5]
            sid = lookup[f'{country}/{transaction}']
            calls.append((cycle[0], sid, now[0]))
            if sid != selected[-1]:
                return httpx.Response(200, text='invalid publisher table')
            text = 'REF_AREA,SECTOR,ACCOUNTING_ENTRY,TRANSACTION,INSTR_ASSET,UNIT_MULT,TIME_PERIOD,OBS_VALUE\n'
            text += f"{country},S11,{entry},{'_Z' if stock else transaction},{transaction if stock else '_Z'},6,2024,{100 + cycle[0]}\n"
            return httpx.Response(200, text=text)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            engine = create_engine('sqlite+pysqlite:///' + str(root/'observations.sqlite'))
            Base.metadata.create_all(engine)
            gate = SourcePolicyGate(state_path=root/'policy.sqlite', clock=lambda: now[0],
                                    sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
            with patch.dict('os.environ', {'FINANCE_SOURCE_POLICY_ACKNOWLEDGED': 'oecd-sdmx',
                                           'FINANCE_SOURCE_EVIDENCE_DIR': str(root/'evidence')}), \
                 managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http, \
                 patch('finance_dashboard.worker.ProviderRouter', side_effect=lambda: ProviderRouter(http)), \
                 patch('finance_dashboard.worker.record_event'), \
                 patch('finance_dashboard.service.now_utc', side_effect=lambda: datetime.fromtimestamp(now[0], timezone.utc)):
                try:
                    for day in range(3):
                        cycle[0] = day
                        refresh_all(engine, providers={'OECD_NFC_ACCOUNTS'}, series_ids=set(selected))
                        self.assertEqual(sum(c == day for c, _, _ in calls), 20)
                        now[0] += 86400
                    self.assertEqual([c for c, sid, _ in calls if sid == selected[-1]], [1, 2])
                    for _, _, at in calls:
                        self.assertLessEqual(sum(at - 3600 < t <= at for _, _, t in calls), 20)
                finally:
                    engine.dispose()

    def test_next_cycle_prioritizes_uncollected_series_under_real_oecd_quota(self):
        definitions = {row["id"]: row for row in load_documents()[0]["series"]
                       if row["provider"] == "OECD_NFC_ACCOUNTS"}
        selected = sorted(definitions)[:21]
        by_source_key = {definitions[sid]["source_key"]: sid for sid in selected}
        now = [1_794_384_000.0]
        calls = []
        def sleep(seconds):
            now[0] += seconds
        def respond(request):
            dims = request.url.path.rsplit("/", 1)[-1].split(".")
            country, entry = dims[1], dims[4]
            stock = "DF_TABLE9B" in request.url.path
            transaction = dims[6] if stock else dims[5]
            calls.append((by_source_key[f"{country}/{transaction}"], dict(request.url.params), now[0]))
            header = ("REF_AREA,SECTOR,ACCOUNTING_ENTRY,TRANSACTION,INSTR_ASSET,UNIT_MULT,TIME_PERIOD,OBS_VALUE\n")
            row = f"{country},S11,{entry},{'_Z' if stock else transaction},{transaction if stock else '_Z'},6,2024,100\n"
            return httpx.Response(200, text=header + row)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            url = "sqlite+pysqlite:///" + str(root / "observations.sqlite")
            engine = create_engine(url)
            Base.metadata.create_all(engine)
            gate = SourcePolicyGate(state_path=root / "policy.sqlite", clock=lambda: now[0], sleep=sleep)
            with patch.dict("os.environ", {
                    "FINANCE_SOURCE_POLICY_ACKNOWLEDGED": "oecd-sdmx",
                    "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence")}), \
                    managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http, \
                    patch("finance_dashboard.worker.ProviderRouter", side_effect=lambda: ProviderRouter(http)), \
                    patch("finance_dashboard.worker.record_event"):
                try:
                    first = refresh_all(engine, providers={"OECD_NFC_ACCOUNTS"}, series_ids=set(selected))
                    self.assertEqual(first, 1)
                    self.assertEqual([sid for sid, _, _ in calls], selected[:20])
                    engine.dispose()
                    engine = create_engine(url)  # Ordering must survive a process/connection restart.
                    now[0] += 3600
                    second = refresh_all(engine, providers={"OECD_NFC_ACCOUNTS"}, series_ids=set(selected))
                    self.assertEqual(second, 1)
                    self.assertEqual(len(calls), 40)
                    self.assertEqual(calls[20][0], selected[20])
                    self.assertNotIn("startPeriod", calls[20][1])  # Never-collected still requests full history.
                    self.assertTrue(all(params.get("startPeriod") == "2019" for _, params, _ in calls[21:]))
                    with Session(engine) as session:
                        successful = session.scalar(select(func.count(func.distinct(IngestionRun.series_id)))
                            .where(IngestionRun.status == "success"))
                        self.assertEqual(successful, 21)
                        self.assertEqual(session.scalar(select(func.count()).select_from(IngestionRun)), 42)
                    for _, _, at in calls:
                        self.assertLessEqual(sum(at - 3600 < when <= at for _, _, when in calls), 20)
                finally:
                    engine.dispose()
