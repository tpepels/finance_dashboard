"""Full offline source-identity and arithmetic tests for free EU27 macro series."""
from datetime import date
from decimal import Decimal
from unittest import TestCase
import httpx
from finance_dashboard.eurostat_corporate import (
    EurostatMacroError, eu27_corporate_gross_surplus_gdp,
    parse_eurostat_annual_series,
)
from finance_dashboard.providers import ProviderRouter

def payload(*, dataset="nasa_10_nf_tr", sector="S11", na_item="B2A3G",
            unit="CP_MEUR", direct="RECV", geo="EU27_2020", years=None, values=None):
    if years is None:
        years=["2023","2024","2025"]
    if values is None:
        values={"0":1000,"1":1100,"2":1200}
    fields=[("freq","A"),("unit",unit)]
    if dataset=="nasa_10_nf_tr":
        fields.append(("direct",direct))
    fields.extend([("na_item",na_item),("sector",sector),("geo",geo)])
    fields.append(("time",None))
    dims={name:{"category":{"index":({val:0} if val else {y:i for i,y in enumerate(years)})}} for name,val in fields}
    return {"version":"2.0","class":"dataset","source":"ESTAT",
            "id":[name for name,_ in fields],
            "size":[1]*(len(fields)-1)+[len(years)],
            "dimension":dims,"value":values}

class EurostatCorporateParserTests(TestCase):
    def test_identity_precision_missing_and_start(self):
        raw=payload(values={"0":1000.25,"2":1250})
        got=parse_eurostat_annual_series(raw,dataset="nasa_10_nf_tr",sector="S11",
                    na_item="B2A3G",unit="CP_MEUR",direct="RECV")
        self.assertEqual(got,{date(2023,1,1):Decimal("1000.25"),date(2025,1,1):Decimal(1250)})
        newer=parse_eurostat_annual_series(raw,dataset="nasa_10_nf_tr",sector="S11",
                   na_item="B2A3G",unit="CP_MEUR",direct="RECV",start=date(2024,1,1))
        self.assertEqual(newer,{date(2025,1,1):Decimal(1250)})

    def test_invalid_sector_currency_geography_direction_dimension_and_nonfinite(self):
        raw=payload()
        for change in [
            lambda p: p.update(source="NOT_ESTAT"),
            lambda p: p["dimension"]["sector"]["category"]["index"].update({"S12":1}),
            lambda p: p["dimension"]["geo"]["category"]["index"].update({"USA":1}),
            lambda p: p["dimension"]["direct"]["category"]["index"].update({"PAID":1}),
            lambda p: p["dimension"]["unit"]["category"]["index"].update({"USD":1}),
            lambda p: p["dimension"]["time"]["category"]["index"].update({"2022":2}),
            lambda p: p["value"].update({"0":float("inf")}),
        ]:
            import copy
            p=copy.deepcopy(raw)
            change(p)
            with self.assertRaises(EurostatMacroError):
                parse_eurostat_annual_series(p,dataset="nasa_10_nf_tr",sector="S11",
                     na_item="B2A3G",unit="CP_MEUR",direct="RECV")

    def test_nfc_direct_published_profit_share_is_percent_of_gva(self):
        p=payload(dataset="nasa_10_ki",sector="S11",na_item="B2G_B3G_RAT_S11",
                  unit="PC",values={"0":41.46,"1":40.05,"2":39.83})
        got=parse_eurostat_annual_series(p,dataset="nasa_10_ki",sector="S11",
                 na_item="B2G_B3G_RAT_S11",unit="PC")
        self.assertEqual(got[date(2025,1,1)],Decimal("39.83"))

    def test_correct_eu_financial_plus_nonfinancial_over_total_gdp(self):
        a={date(2023,1,1):Decimal(20),date(2024,1,1):Decimal(23)}
        b={date(2023,1,1):Decimal(5)}
        g={date(2023,1,1):Decimal(100),date(2024,1,1):Decimal(115)}
        self.assertEqual(eu27_corporate_gross_surplus_gdp(a,b,g),
                         {date(2023,1,1):Decimal(25)})
        self.assertNotIn(date(2024,1,1),eu27_corporate_gross_surplus_gdp(a,b,g))
        with self.assertRaises(EurostatMacroError):
            eu27_corporate_gross_surplus_gdp(a,{date(2023,1,1):Decimal(-3)},g)
        with self.assertRaises(EurostatMacroError):
            eu27_corporate_gross_surplus_gdp(a,{},g)
        with self.assertRaises(EurostatMacroError):
            eu27_corporate_gross_surplus_gdp(a,b,{date(2023,1,1):Decimal(0)})

class EurostatCorporateRouterTests(TestCase):
    def test_three_bound_accounts_and_eu_gdp_matched(self):
        seen=[]
        def handler(request):
            p=request.url.params
            seen.append(dict(p))
            self.assertEqual(p.get("geo"),"EU27_2020")
            self.assertEqual(p.get("direct"),"RECV")
            vals={"S11":{"0":25,"1":28},"S12":{"0":5,"1":6},"S1":{"0":100,"1":105}}
            return httpx.Response(200,json=payload(
                sector=p["sector"],na_item=p["na_item"],unit=p["unit"],
                values=vals[p["sector"]],years=["2024","2025"]))
        router=ProviderRouter(httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            got=router.fetch("profit.eu27.corporate_operating_surplus_gdp")
            self.assertEqual(got.observations,
              {date(2024,1,1):Decimal(30),date(2025,1,1):Decimal(3400)/Decimal(105)})
            self.assertEqual(set(x["sector"] for x in seen),{"S11","S12","S1"})
        finally:
            router.close()

    def test_independent_official_eurostat_nfc_gva_ratio(self):
        def handler(request):
            p=request.url.params
            self.assertEqual(p["na_item"],"B2G_B3G_RAT_S11")
            self.assertEqual(p["unit"],"PC")
            return httpx.Response(200,json=payload(dataset="nasa_10_ki",
                sector="S11",na_item=p["na_item"],unit="PC",
                values={"0":40.12,"1":39.96,"2":41.37}))
        router=ProviderRouter(httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            got=router.fetch("profit.eu27.nonfinancial_gross_surplus_value_added")
            self.assertEqual(got.observations[date(2025,1,1)],Decimal("41.37"))
        finally:
            router.close()
