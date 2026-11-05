"""Factual publisher excerpts exercise independent selectors and native archives."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
import zipfile

import httpx
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents
from finance_dashboard.captured_sources import _imf_mapper,_bea_q,_pink_sheet,_shiller,_ecb,_bis,_bis_policy_metadata
from finance_dashboard.database import Base,make_engine
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.provider_parsers import PINK_SHEET_URL
from finance_dashboard.remaining_sources import BEA_Q_URL
from finance_dashboard.service import IngestionService,current_observations
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_reconciliation import EvidenceError,reconcile

FIXTURE=Path(__file__).parent/'fixtures/native_source_families'


def xlsx_from_factual_cells(rows,sheet_name):
    """Test transport container; copied native cell values are unchanged.

    This generated fixture workbook is not represented as the publisher's full
    original. sources.json separately pins the original and selected excerpts.
    """
    def column(number):
        result=''
        while number:
            number,remainder=divmod(number-1,26);result=chr(65+remainder)+result
        return result
    records=[]
    for row_index,row in enumerate(rows,1):
        cells=[]
        for index,value in enumerate(row,1):
            if value is None: continue
            key=column(index)+str(row_index)
            if isinstance(value,(int,float)):
                cells.append(f'<c r="{key}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{key}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        records.append(f'<row r="{row_index}">'+''.join(cells)+'</row>')
    main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    package=io.BytesIO()
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml',f'<workbook xmlns="{main}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{main}"><sheetData>'+''.join(records)+'</sheetData></worksheet>')
    return package.getvalue()


class CapturedSourceFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry={row['id']:row for row in load_documents()[0]['series']}

    def test_publisher_fixture_hashes_and_original_selection_provenance(self):
        for source in json.loads((FIXTURE/'sources.json').read_text()):
            self.assertEqual(sha256((FIXTURE/source['file']).read_bytes()).hexdigest(),source['fixture_sha256'])
            self.assertRegex(source['original_sha256'],r'^[0-9a-f]{64}$')
            self.assertTrue(source['source_url'].startswith('https://'))

    def test_imf_native_units_database_edition_and_projection_boundary_are_distinct(self):
        payload=json.loads((FIXTURE/'imf_pcpipch.json').read_text())
        definition=self.registry['prices.us.imf_cpi_inflation']
        values,proof=_imf_mapper(payload,definition,'https://www.imf.org/external/datamapper/api/v2/PCPIPCH')
        self.assertEqual(values[date(1980,1,1)],Decimal('13.5'))
        self.assertEqual(values[date(2025,1,1)],Decimal('2.7'))
        self.assertNotIn(date(2026,1,1),values)
        self.assertEqual(proof['source_projection_start_year'],2026)
        self.assertEqual(proof['source_database_vintage'],'World Economic Outlook (October 2026)')
        self.assertFalse(proof['individual_observation_first_publication_verified'])
        payload['indicators']['PCPIPCH']['projection-year']=2025
        earlier,_proof=_imf_mapper(payload,definition,'https://www.imf.org/external/datamapper/api/v2/PCPIPCH')
        self.assertNotIn(date(2025,1,1),earlier)
        payload['indicators']['PCPIPCH']['unit']='Index'
        with self.assertRaises(EvidenceError):
            _imf_mapper(payload,definition,'https://www.imf.org/external/datamapper/api/v2/PCPIPCH')

    def test_bea_distinct_original_q_columns_and_ambiguous_table_rejection(self):
        html=(FIXTURE/'bea_table_e.html').read_text()
        for sid,value in [('valuation.us.tobins_q','2.26'),('valuation.us.tobins_q2','2.54'),('valuation.us.tobins_q3','2.08')]:
            values=_bea_q(html,self.registry[sid],BEA_Q_URL)
            self.assertEqual(len(values),65)
            self.assertEqual(values[date(2024,1,1)],Decimal(value))
        with self.assertRaises(EvidenceError): _bea_q(html+html,self.registry['valuation.us.tobins_q'],BEA_Q_URL)

    def test_pink_sheet_preserves_gold_troy_ounce_and_brent_barrel_native_columns(self):
        rows=json.loads((FIXTURE/'pink_gold_brent_cells.json').read_text())['rows']
        original=xlsx_from_factual_cells(rows,'Monthly Prices')
        gold,gold_meta=_pink_sheet(original,self.registry['gold.usd.monthly_average'],PINK_SHEET_URL)
        brent,brent_meta=_pink_sheet(original,self.registry['prices.commodity.brent_usd'],PINK_SHEET_URL)
        self.assertEqual((len(gold),len(brent)),(802,802))
        self.assertEqual(gold[date(1960,1,1)],Decimal('35.0'))
        self.assertEqual(brent[date(1960,1,1)],Decimal('1.6'))
        self.assertEqual(gold_meta['source_native_unit'],'usd_per_oz')
        self.assertEqual(brent_meta['source_native_unit'],'usd_per_barrel')
        changed=json.loads(json.dumps(rows))
        for row in changed:
            for column,value in enumerate(row):
                if isinstance(value,str) and 'troy oz' in value: row[column]='($/kg)'
        with self.assertRaises(EvidenceError):
            _pink_sheet(xlsx_from_factual_cells(changed,'Monthly Prices'),self.registry['gold.usd.monthly_average'],PINK_SHEET_URL)

    def test_shiller_ordinary_cape_is_not_total_return_cape_and_link_identity_is_required(self):
        rows=json.loads((FIXTURE/'shiller_cape_cells.json').read_text())['rows']
        original=xlsx_from_factual_cells(rows,'Data')
        source=next(source for source in json.loads((FIXTURE/'sources.json').read_text()) if source['file']=='shiller_cape_cells.json')
        homepage=(FIXTURE/'shiller_download_link.html').read_text()
        values=_shiller(original,self.registry['valuation.us.cape'],homepage,'https://shillerdata.com/',source['source_url'])
        self.assertEqual(len(values),1750)
        self.assertEqual(min(values),date(1881,1,1))
        self.assertEqual(max(values),date(2026,10,1))
        with self.assertRaises(EvidenceError):
            _shiller(original,self.registry['valuation.us.cape'],homepage,'https://shillerdata.com/','https://unapproved.example/ie_data.xls')

    def test_all_four_families_enter_append_only_ingestion_and_independent_reconciliation(self):
        pink=xlsx_from_factual_cells(json.loads((FIXTURE/'pink_gold_brent_cells.json').read_text())['rows'],'Monthly Prices')
        shiller=xlsx_from_factual_cells(json.loads((FIXTURE/'shiller_cape_cells.json').read_text())['rows'],'Data')
        ids=['prices.us.imf_cpi_inflation','external.us.current_account_gdp','fiscal.world.public_debt',
             'valuation.us.tobins_q','valuation.us.tobins_q2','valuation.us.tobins_q3',
             'gold.usd.monthly_average','prices.commodity.brent_usd','valuation.us.cape']
        def source(request):
            if '/api/v2/' in request.url.path:
                return httpx.Response(200,content=(FIXTURE/('imf_'+request.url.path.rsplit('/',1)[-1].lower()+'.json')).read_bytes())
            if request.url.host=='apps.bea.gov': return httpx.Response(200,content=(FIXTURE/'bea_table_e.html').read_bytes())
            if request.url.host=='thedocs.worldbank.org': return httpx.Response(200,content=pink)
            if request.url.host=='shillerdata.com': return httpx.Response(200,content=(FIXTURE/'shiller_download_link.html').read_bytes())
            if request.url.host=='img1.wsimg.com': return httpx.Response(200,content=shiller)
            raise AssertionError('Unexpected test source')
        with TemporaryDirectory() as tmp:
            root=Path(tmp);url='sqlite:///'+str(root/'history.db');engine=make_engine(url);Base.metadata.create_all(engine)
            with httpx.Client(transport=httpx.MockTransport(source)) as http:
                service=IngestionService(engine,SourceAcquisition(ProviderRouter(http),root))
                for sid in ids:
                    first=service.refresh(sid,full=True);repeat=service.refresh(sid,full=True)
                    self.assertGreater(first['versions_added'],0)
                    self.assertEqual(repeat['versions_added'],0)
            report=reconcile(url,root,ids)
            self.assertTrue(report['passed'],report)
            self.assertEqual(report['matched_series'],len(ids))
            with Session(engine) as session:
                self.assertEqual(len(current_observations(session,'valuation.us.cape')),1750)
            engine.dispose()

    def test_original_ecb_and_bis_policy_dimensions_units_negative_values_and_splice_notes(self):
        ecb=(FIXTURE/'ecb_deposit_excerpt.csv').read_text()
        ecb_url='https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?format=csvdata'
        values,metadata=_ecb(ecb,self.registry['policy_rate.ea.ecb_dfr'],ecb_url)
        self.assertEqual(len(values),3)
        self.assertTrue(any(value<0 for value in values.values()))
        self.assertEqual(metadata['source_native_unit_codes'],['PCPA'])
        for area,sid in [('us','policy_rate.us.bis'),('xm','policy_rate.ea.bis'),('jp','policy_rate.jp.bis')]:
            payload=json.loads((FIXTURE/f'bis_policy_{area}.json').read_text())
            values=_bis(payload,self.registry[sid]);proof=_bis_policy_metadata(payload)
            self.assertGreater(len(values),1)
            self.assertEqual(proof['source_native_unit_label'],'Per cent per year')
            self.assertFalse(proof['individual_observation_first_publication_verified'])
            if area=='us': self.assertIn('mid-point',proof['source_publisher_metadata']['COMPILATION'])
            if area=='jp':
                with self.assertRaises(EvidenceError): _bis(payload,self.registry['policy_rate.us.bis'])
        with self.assertRaises(EvidenceError):
            _ecb(ecb.replace('PCPA','INDEX'),self.registry['policy_rate.ea.ecb_dfr'],ecb_url)

    def test_daily_policy_originals_enter_capture_router_and_independent_reconciliation(self):
        ids=['policy_rate.us.bis','policy_rate.ea.bis','policy_rate.jp.bis','policy_rate.ea.ecb_dfr']
        def source(request):
            if request.url.host=='stats.bis.org':
                area=request.url.path.rsplit('.',1)[-1].lower()
                return httpx.Response(200,content=(FIXTURE/f'bis_policy_{area}.json').read_bytes(),headers={'content-type':'application/vnd.sdmx.data+json'})
            return httpx.Response(200,content=(FIXTURE/'ecb_deposit_excerpt.csv').read_bytes())
        with TemporaryDirectory() as tmp:
            root=Path(tmp);url='sqlite:///'+str(root/'daily.db');engine=make_engine(url);Base.metadata.create_all(engine)
            with httpx.Client(transport=httpx.MockTransport(source)) as http:
                service=IngestionService(engine,SourceAcquisition(ProviderRouter(http),root))
                for sid in ids: self.assertGreater(service.refresh(sid,full=True)['received'],1)
            report=reconcile(url,root,ids)
            self.assertTrue(report['passed'],report)
            self.assertEqual(report['matched_series'],4)
            engine.dispose()


if __name__=='__main__': unittest.main()
