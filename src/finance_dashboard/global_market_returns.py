"""Audit the original Doeswijk–Swinkels monthly global multiasset output.

Read cached native XML values; never follow external workbook links or recalc
source formulae. A failed source identity remains a failed source identity.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from .bis import ProviderError
from .research_returns import ReturnsBundle, _number, _zip_members

SOURCE_URL="https://laurensswinkels.com/wp-content/uploads/2025/11/public-data-file-jimf-3.xlsx"
ORIGINAL_SHA256="a66ce1c1c1852fbac0c5c56bfe8b02c42900a5a820c9f13f2219325486c96d2d"
CURRENCIES=("AUD","CAD","EUR","JPY","NZD","NOK","SEK","CHF","GBP","USD")
TYPES=("NOMINAL","REAL","EXCESS")
NAMESPACE="http://purl.oclc.org/ooxml/spreadsheetml/main"
NS={"m":NAMESPACE}
SOURCE_IDENTITY={"publisher":"Doeswijk and Swinkels", "doi":"10.1016/j.jimonfin.2025.103453",
                 "original_sha256":ORIGINAL_SHA256}
# A source inconsistency blocks the affected pair, not the original bytes or
# the 29 separately checked published pairs. It remains visible in the audit.
GLOBAL_MARKET_SERIES={
    f"returns.doeswijk_swinkels.global_multiasset.{currency.lower()}.{kind.lower()}":(currency,kind)
    for currency in CURRENCIES for kind in TYPES if (currency,kind)!=("EUR","NOMINAL")
}


def check_index_return_pair(*, previous_index: str, current_index: str,
                            published_return_percent: str) -> dict:
    """Return = 100 * (index / previous index - 1), in percentage points.

    The numerical bound propagates half a unit at 15 significant decimal
    digits for each Excel cell, plus 16 binary64 epsilons for the arithmetic
    producing cached results. It cannot excuse a substantive source mismatch.
    """
    a,b,r=(_number(v) for v in (previous_index,current_index,published_return_percent))
    if a<=0 or b<=0:
        raise ProviderError("Global market return index must be positive")
    def half_quantum(value):
        return Decimal(5).scaleb(value.adjusted()-15) if value else Decimal("5e-15")
    with localcontext() as ctx:
        ctx.prec=50
        da,db,dr=(half_quantum(v) for v in (a,b,r))
        derived=(b/a-1)*100
        ratio=b/a
        bound=100*(db/(a-da)+abs(b)*da/((a-da)*a))+dr
        bound+=100*16*(Decimal(2)**-52)*(1+abs(ratio))
        residual=abs(derived-r)
        return {"derived_return_percent":str(derived),
                "absolute_residual_percentage_points":str(residual),
                "numeric_bound_percentage_points":str(bound),
                "within_numeric_bound":residual<=bound}


def _column(number: int) -> str:
    result=""
    while number:
        number,remainder=divmod(number-1,26)
        result=chr(65+remainder)+result
    return result


def _original_cells(original: bytes) -> dict:
    if sha256(original).hexdigest()!=ORIGINAL_SHA256:
        raise ProviderError("Original global market workbook SHA mismatch")
    members=_zip_members(original,maximum=15_000_000)
    try:
        book=ET.fromstring(members["xl/workbook.xml"])
        if [s.attrib["name"] for s in book.findall("m:sheets/m:sheet",NS)]!=["GMP JIMF"]:
            raise ValueError("sheet identity")
        strings=["".join(part.text or "" for part in s.iter("{"+NAMESPACE+"}t"))
                 for s in ET.fromstring(members["xl/sharedStrings.xml"])]
        sheet=ET.fromstring(members["xl/worksheets/sheet1.xml"])
        cells={}
        for cell in sheet.findall("m:sheetData/m:row/m:c",NS):
            value=cell.find("m:v",NS)
            if value is not None:
                cells[cell.attrib["r"]]=strings[int(value.text)] if cell.attrib.get("t")=="s" else value.text
        if "Doeswijk and Swinkels (2026)" not in cells["B1"]:
            raise ValueError("research identity")
        return cells
    except (ValueError,KeyError,TypeError,IndexError,ET.ParseError) as exc:
        raise ProviderError("Original global market workbook structure invalid") from exc


def audit_global_market_workbook(original: bytes) -> dict:
    """Reproduce every published cached index/return identity for this edition."""
    cells=_original_cells(original)
    try:
        series=[]
        for block,currency in enumerate(CURRENCIES):
            offset=block*8
            if cells[_column(offset+1)+"3"]!=currency:
                raise ValueError("currency identity")
            dates=[date.fromisoformat(cells[_column(offset+1)+str(row)]) for row in range(5,642)]
            if dates[0]!=date(1969,12,31) or dates[-1]!=date(2022,12,31):
                raise ValueError("original date bounds")
            if any((b.year*12+b.month)-(a.year*12+a.month)!=1 for a,b in zip(dates,dates[1:])):
                raise ValueError("original monthly period sequence")
            for kind,return_type in enumerate(TYPES):
                index_col=_column(offset+2+kind)
                return_col=_column(offset+5+kind)
                if cells[index_col+"4"]!=return_type or cells[return_col+"4"]!=return_type:
                    raise ValueError("index/return column identity")
                checks=[]
                failures=[]
                for row in range(6,642):
                    check=check_index_return_pair(previous_index=cells[index_col+str(row-1)],
                        current_index=cells[index_col+str(row)],
                        published_return_percent=cells[return_col+str(row)])
                    checks.append(check)
                    if not check["within_numeric_bound"]:
                        failures.append({"source_row":row,"source_date":dates[row-5].isoformat(),
                            "index_cell":index_col+str(row),"return_cell":return_col+str(row),
                            "previous_index":cells[index_col+str(row-1)],"current_index":cells[index_col+str(row)],
                            "published_return_percent":cells[return_col+str(row)],**check})
                series.append({"currency":currency,"return_type":return_type,
                    "native_return_units":"percent","native_index_base":"December 1969 approximately 100",
                    "identity_checks":len(checks),"identity_failures":len(failures),
                    "maximum_absolute_residual_percentage_points":str(max(Decimal(c["absolute_residual_percentage_points"]) for c in checks)),
                    "failures":failures})
    except (ValueError,KeyError,TypeError,ET.ParseError) as exc:
        raise ProviderError("Original global market workbook structure invalid") from exc
    failed=any(s["identity_failures"] for s in series)
    return {"schema_version":1,"source":"DOESWIJK_SWINKELS_GLOBAL_MULTI_ASSET_ORIGINAL_OUTPUT",
        "source_url":SOURCE_URL,"original_sha256":ORIGINAL_SHA256,
        "research_doi":"10.1016/j.jimonfin.2025.103453",
        "status":"original_index_return_identity_failed" if failed else "cached_index_return_identities_pass",
        "publisher_correction_note":cells["A2"],"months":636,"first_month":"1970-01","last_month":"2022-12",
        "series_pairs":len(series),"series":series,
        "numeric_bound_method":"15 significant decimal cell precision propagated through ratio, plus 16 binary64 epsilons; no fitted residual tolerance",
        "source_values_modified":False,"external_links_followed":False,"formulae_recalculated":False,
        "original_equity_or_bond_benchmark":False,"release_vintages_verified":False,
        "limits":"Published global invested multiasset portfolio output, not separate equity or aggregate-bond index. Source return labels retained; EUR nominal index and return inconsistency prevents a synchronized cross-currency corpus claim. Current published caches do not establish first releases or independently reconstruct CPI, FX, risk-free rates, weights and constituent history."}


def parse_global_market_workbook(original: bytes) -> ReturnsBundle:
    """Select consistent published pairs without repairing failed source values.

    Monthly storage keys label the source month, while the exact source dates
    (which may be trading days) remain part of each native return window.
    """
    report=audit_global_market_workbook(original)
    cells=_original_cells(original)
    checks={(s["currency"],s["return_type"]):s for s in report["series"]}
    observations,series={},{}
    for sid,(currency,kind) in GLOBAL_MARKET_SERIES.items():
        check=checks[(currency,kind)]
        if check["identity_failures"]:
            raise ProviderError("Selected global multiasset index/return identity failed")
        offset=CURRENCIES.index(currency)*8
        kind_offset=TYPES.index(kind)
        date_column=_column(offset+1)
        index_column=_column(offset+2+kind_offset)
        return_column=_column(offset+5+kind_offset)
        values,periods,windows,indices={},{},{},{}
        for row in range(6,642):
            source_date=date.fromisoformat(cells[date_column+str(row)])
            period=source_date.replace(day=1)
            values[period]=_number(cells[return_column+str(row)])
            periods[period.isoformat()]=source_date.isoformat()
            windows[period.isoformat()]={"start_exclusive":cells[date_column+str(row-1)],
                                        "end_inclusive":source_date.isoformat()}
            indices[period.isoformat()]={"previous":cells[index_column+str(row-1)],
                                        "current":cells[index_column+str(row)]}
        observations[sid]=values
        series[sid]={"currency":currency,"return_type":kind,"source_sheet":"GMP JIMF",
            "source_date_column":date_column,"source_index_column":index_column,
            "source_return_column":return_column,"source_periods":periods,
            "source_return_windows":windows,"native_index_controls":indices,
            "index_return_identity_checks":check["identity_checks"],"index_return_identity_failures":0,
            "return_convention":"Publisher global invested multiasset research portfolio monthly "+kind.lower()+" return; native percent."}
    return ReturnsBundle(observations,{
        "publisher":"Doeswijk and Swinkels","research_doi":"10.1016/j.jimonfin.2025.103453",
        "original_sha256":ORIGINAL_SHA256,"native_frequency":"M","native_unit":"percent",
        "original_first_publication_at":None,"dataset_release_at":None,
        "source_edition":"Pinned publisher workbook, path 2025/11; path and citation year are not verified release dates.",
        "period_key":"First calendar day labels source month; exact prior/current publisher dates retained without calendar-day interpolation.",
        "series":series,"excluded_source_pairs":[{"currency":s["currency"],"return_type":s["return_type"],
            "identity_failures":s["identity_failures"]} for s in report["series"] if s["identity_failures"]],
        "source_workbook_audit_status":report["status"],"publisher_correction_note":report["publisher_correction_note"],
        "measurement_note":report["limits"],"source_values_modified":False,
        "original_equity_or_bond_benchmark":False,"release_vintages_verified":False,
    })


def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description="Read-only original global multiasset workbook identity audit")
    parser.add_argument("--file",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    report=audit_global_market_workbook(args.file.read_bytes())
    rendered=json.dumps(report,indent=2)+"\n"
    if args.output:
        with args.output.open("x",encoding="utf-8") as stream:
            stream.write(rendered)
    print(json.dumps({k:v for k,v in report.items() if k!="series"},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
