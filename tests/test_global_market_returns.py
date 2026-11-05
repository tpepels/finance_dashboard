"""Original cached author output must retain its scientific inconsistencies."""
import json
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

FIXTURE=Path(__file__).parent/"fixtures/research_returns/global_market_index_return_excerpt.json"


class GlobalMarketReturnsTests(unittest.TestCase):
    def test_factual_original_pairs_distinguish_large_failure_from_serialization(self):
        from finance_dashboard.global_market_returns import check_index_return_pair
        examples=json.loads(FIXTURE.read_text())["pairs"]
        checks=[check_index_return_pair(**{k:p[k] for k in (
            "previous_index","current_index","published_return_percent")}) for p in examples]
        self.assertEqual([c["within_numeric_bound"] for c in checks],[False,False,True,True])
        self.assertGreater(float(checks[1]["absolute_residual_percentage_points"]),2.4)
        self.assertLess(float(checks[2]["numeric_bound_percentage_points"]),1e-9)

    def test_undefined_previous_index_cannot_pass_an_identity_check(self):
        from finance_dashboard.global_market_returns import check_index_return_pair
        from finance_dashboard.bis import ProviderError
        for invalid in ("0","NaN","-1"):
            with self.assertRaises(ProviderError):
                check_index_return_pair(previous_index=invalid,current_index="100",published_return_percent="1")

    @unittest.skipUnless(os.environ.get('TEST_GLOBAL_MARKET_PACKAGE'),'private original author workbook supplied separately')
    def test_usable_pair_enters_canonical_provider_and_independent_original_reconciliation(self):
        from finance_dashboard.global_market_returns import GLOBAL_MARKET_SERIES,parse_global_market_workbook
        from finance_dashboard.research_returns import ResearchReturnsClient
        from finance_dashboard.return_source_reconciliation import read_return_originals
        from finance_dashboard.source_reconciliation import _selected_manifest,_original_file,EvidenceError
        from finance_dashboard.bis import ProviderError
        original=Path(os.environ['TEST_GLOBAL_MARKET_PACKAGE']).read_bytes()
        sid='returns.doeswijk_swinkels.global_multiasset.usd.nominal'
        excluded='returns.doeswijk_swinkels.global_multiasset.eur.nominal'
        self.assertNotIn(excluded,GLOBAL_MARKET_SERIES)
        bundle=parse_global_market_workbook(original)
        self.assertEqual(len(bundle.observations),29)
        self.assertEqual(sum(len(values) for values in bundle.observations.values()),29*636)
        self.assertEqual(bundle.observations[sid][date(1970,1,1)],Decimal('-2.985057035631522'))
        self.assertEqual(bundle.metadata['series'][sid]['source_periods']['1970-01-01'],'1970-01-30')
        self.assertEqual(bundle.metadata['series'][sid]['source_return_windows']['1970-01-01'],
            {'start_exclusive':'1969-12-31','end_inclusive':'1970-01-30'})
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=original,request=request))) as http:
                client=ResearchReturnsClient(http,archive_dir=root)
                actual=client.fetch(sid,date(2022,12,1))
                self.assertEqual(actual.observations,{date(2022,12,1):Decimal('-1.825361623285382')})
                with self.assertRaises(ProviderError): client.fetch(excluded)
            selected,evidence=read_return_originals(root,list(GLOBAL_MARKET_SERIES),_selected_manifest,_original_file)
            self.assertEqual(selected,bundle.observations)
            self.assertFalse(evidence[sid]['original_equity_or_bond_benchmark'])
            self.assertEqual(evidence[sid]['source_workbook_audit_status'],'original_index_return_identity_failed')
            path=next(root.rglob('source.xlsx'))
            path.write_bytes(original+b'tampered')
            with self.assertRaises(EvidenceError):
                read_return_originals(root,[sid],_selected_manifest,_original_file)

    @unittest.skipUnless(os.environ.get('TEST_GLOBAL_MARKET_PACKAGE'),'private original author workbook supplied separately')
    def test_router_append_only_ingestion_and_native_reconciliation_for_named_usd_multiasset_series(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from finance_dashboard.catalog import load_documents,validate
        from finance_dashboard.database import Base,make_engine,IngestionRun
        from finance_dashboard.providers import ProviderRouter
        from finance_dashboard.provider_parsers import SourceUnavailable
        from finance_dashboard.service import IngestionService,current_observations
        from finance_dashboard.source_reconciliation import reconcile
        sid='returns.doeswijk_swinkels.global_multiasset.usd.nominal'
        docs,charts=load_documents()
        self.assertEqual(validate(docs,charts),[])
        definition=next(d for d in docs['series'] if d['id']==sid)
        self.assertEqual(definition['provider'],'GLOBAL_MARKET_RETURNS')
        self.assertEqual(definition['source_key'],'GMP JIMF/USD/NOMINAL/cached_percent_return')
        original=Path(os.environ['TEST_GLOBAL_MARKET_PACKAGE']).read_bytes()
        with TemporaryDirectory() as tmp,patch.dict(os.environ,{'FINANCE_SOURCE_EVIDENCE_DIR':tmp}):
            root=Path(tmp)
            url='sqlite:///'+str(root/'test.db')
            engine=make_engine(url);Base.metadata.create_all(engine)
            with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=original,request=request))) as http:
                router=ProviderRouter(http)
                service=IngestionService(engine,router)
                first=service.refresh(sid)
                again=service.refresh(sid)
                self.assertEqual((first['received'],first['versions_added']),(636,636))
                self.assertEqual((again['received'],again['versions_added']),(636,0))
                original_definition=router.definitions[sid]
                for invalid in ({'source_key':'GMP JIMF/USD/NOMINAL/ratio'},
                                {'unit':'ratio'},{'currency':'EUR'},{'frequency':'A'}):
                    router.definitions[sid]={**original_definition,**invalid}
                    with self.assertRaises(SourceUnavailable): router.fetch(sid)
            with Session(engine) as session:
                rows=current_observations(session,sid)
                self.assertEqual(len(rows),636)
                self.assertEqual(rows[0].value,Decimal('-2.9850570356'))
                self.assertTrue(all(run.requested_from is None for run in session.scalars(select(IngestionRun))))
            result=reconcile(url,root,[sid])
            self.assertTrue(result['passed'])
            self.assertEqual(result['series'][0]['source_periods'],636)
            self.assertEqual(result['series'][0]['mismatched_source_values'],[])
            self.assertFalse(result['original_release_vintages_validated'])
            engine.dispose()

    @unittest.skipUnless(os.environ.get("TEST_GLOBAL_MARKET_PACKAGE"),"private original author workbook supplied separately")
    def test_full_original_workbook_retains_579_eur_failures_and_29_consistent_pairs(self):
        from finance_dashboard.global_market_returns import audit_global_market_workbook
        from finance_dashboard.bis import ProviderError
        original=Path(os.environ["TEST_GLOBAL_MARKET_PACKAGE"]).read_bytes()
        report=audit_global_market_workbook(original)
        self.assertEqual(report["status"],"original_index_return_identity_failed")
        self.assertEqual(report["months"],636)
        self.assertEqual(report["first_month"],"1970-01")
        self.assertEqual(report["last_month"],"2022-12")
        self.assertEqual(report["series_pairs"],30)
        failed=[s for s in report["series"] if s["identity_failures"]]
        self.assertEqual([(s["currency"],s["return_type"],s["identity_failures"]) for s in failed],[("EUR","NOMINAL",579)])
        self.assertEqual(sum(s["identity_checks"] for s in report["series"]),19080)
        self.assertIn("government bond series",report["publisher_correction_note"])
        self.assertFalse(report["original_equity_or_bond_benchmark"])
        self.assertFalse(report["release_vintages_verified"])
        with self.assertRaises(ProviderError):
            audit_global_market_workbook(original+b"altered")


if __name__=="__main__": unittest.main()
