"""Archives the engine reads besides stored series: holdings filings and framework originals.

The summaries are pure functions over what the verified readers return; the
loader is thin I/O with a cache keyed on what is stored, so repeated bundles do
not re-read unchanged archives.
"""
from __future__ import annotations

from pathlib import Path


def _pct(value) -> float:
    return float(value)


def nport_filing(record: dict, concentration: dict | None) -> dict:
    """One N-PORT filing: country weights (% of fund NAV), the 12 largest reported issuers and the top-10 share."""
    groups = sorted(((g["reported_name"], _pct(g["share_of_fund_nav_pct"])) for g in (concentration or {}).get("issuer_groups", [])),
                    key=lambda item: item[1], reverse=True)
    return {"date": record["holdings_date"], "accession": record["accession"],
            "countries": {c["country"]: _pct(c["share_of_fund_nav_pct"]) for c in record.get("countries", [])},
            "issuers": [{"name": name, "pct": pct} for name, pct in groups[:12]],
            "top10_pct": sum(pct for _, pct in groups[:10]) if groups else None}


def ucits_summary(record: dict) -> dict:
    """The iShares UCITS file: weights by reported location and sector, and the ten largest positions."""
    countries: dict[str, float] = {}
    sectors: dict[str, float] = {}
    positions = []
    for p in record.get("positions", []):
        weight = _pct(p.get("percent_of_fund_nav") or 0)
        countries[p.get("reported_location") or "Not reported"] = countries.get(p.get("reported_location") or "Not reported", 0) + weight
        sectors[p.get("sector") or "Not reported"] = sectors.get(p.get("sector") or "Not reported", 0) + weight
        positions.append((p.get("name"), weight))
    positions.sort(key=lambda item: item[1], reverse=True)
    return {"date": record.get("holdings_date"), "countries": countries, "sectors": sectors,
            "top": [{"name": name, "pct": pct} for name, pct in positions[:10]]}


_CACHE: dict = {}


def _nport(holdings_root: Path, instrument: str, latest_only: bool = False) -> list[dict]:
    from ..sec_holdings import list_holdings, read_position_source
    out = []
    records = list_holdings(holdings_root, instrument)["records"]
    for record in records[-1:] if latest_only else records:
        key = ("nport", str(holdings_root), instrument, record["accession"])
        if key not in _CACHE:
            try:
                concentration = read_position_source(holdings_root, instrument, record["accession"], summary=True).get(
                    "reported_issuer_concentration")
            except Exception:  # an unreadable original leaves the filing without issuer detail
                concentration = None
            _CACHE[key] = nport_filing(record, concentration)
        out.append(_CACHE[key])
    return out


def load_artifact(name: str, *, evidence_root: Path, holdings_root: Path):
    """Load one named archive; unknown names raise KeyError."""
    if name == 'portfolio_holdings':
        from ..portfolio_holdings import load_portfolio_holdings
        return load_portfolio_holdings()
    if name == "acwi_nport":
        return _nport(Path(holdings_root), "acwi")
    if name in ("vt_nport", "bnd_nport"):
        # Fund exposure needs the latest filing only; a bond fund's 17,000 positions per filing make history costly.
        return _nport(Path(holdings_root), name.split("_")[0], latest_only=True)
    if name == "ucits_world":
        from ..ucits_holdings import read_ucits_sources
        records = read_ucits_sources(Path(holdings_root))["records"]
        return ucits_summary(records[-1]) if records else None
    if name == "shock_events":
        import json
        from ..catalog import DEFAULT_ROOT
        register = DEFAULT_ROOT / "definitions" / "shock_events.json"
        return json.loads(register.read_text())["events"]
    if name == "jst_crises":
        from ..jst import read as read_jst
        return read_jst(Path(evidence_root))
    if name == "rtdsm_sahm":
        from ..philly_rtdsm import read
        return read(Path(evidence_root))
    if name == "nber_chronology":
        from ..nber_chronology import read_nber_chronology
        return read_nber_chronology(Path(evidence_root))
    if name == "owner_inputs":
        from ..owner_inputs import load_owner_inputs
        return load_owner_inputs()
    if name == "cvm_profit_coverage":
        from ..cvm_profits import read_cvm_sources
        report = read_cvm_sources(Path(evidence_root))
        if not report["records"]:
            return None
        # read_cvm_sources verifies original bytes and acquisition receipts.
        # Only native coverage counts are exposed; no income is summed.
        return {"status": report["status"], "sources": [
            {"year": source["archive_year"], **source["population"], "source_url": source["source_url"],
             "original_archive_sha256": source["original_archive_sha256"],
             "evidence_retrieved_at_utc": source["evidence_retrieved_at_utc"]}
            for source in report["records"]],
            "aggregate_produced": False, "listed_population_verified": False,
            "ultimate_parent_deduplication_verified": False,
            "worldwide_population_verified": False}
    if name == "icio_native_direct":
        # Existing canonical original reader; never substitutes reconstructed
        # direct final demand for OECD TiVA FFD_DVA.
        from ..icio_editions import read_edition_archives
        from ..icio_native import canonical_country
        selected = {"USA", "DEU", "FRA", "PRT", "JPN", "CHN", "IND"}
        years = []
        conflicted = []
        for archive in read_edition_archives(Path(evidence_root)):
            if archive.get("source_year_conflict"):
                conflicted.append({
                    "edition": archive["edition"], "filename": archive["filename"],
                    "years": archive["conflicting_years"],
                    "source_sha256": archive["archive_sha256"],
                })
            if archive.get("native_validation_status") not in (
                    "native_accounts_verified",
                    "native_structure_verified_accounting_unavailable"):
                continue  # Incomplete archive years or failed original accounts
            for matrix in archive.get("annual_matrices", []):
                if matrix["year"] in archive.get("conflicting_years", []):
                    continue  # Withhold all incompatible overlapping originals
                # Source accounts for other countries remain directly
                # observable when only a CHN/MEX parent-split rollup is
                # ambiguous. The native audit omits those ambiguous countries.
                countries = {}
                for country, totals in matrix.get("country_direct_flows", {}).items():
                    if country in selected:
                        countries[country] = totals
                years.append({"edition": archive["edition"], "year": matrix["year"],
                    "source": archive["filename"], "source_sha256": archive["archive_sha256"],
                    "accounting_passed": matrix["accounting_passed"],
                    "structure_verified": matrix["structure_verified"],
                    "tiva_reconstruction": matrix.get("tiva_reconstruction"),
                    "accounting_basis": ("publisher_rows_verified" if matrix["accounting_passed"] is True
                        else "source_structure_only_accounts_not_published"),
                    "ambiguous_country_rollups":
                        matrix["country_concordance"]["ambiguous_unsplit_parents"],
                    "countries": countries})
        return {"years": sorted(years, key=lambda x: (x["edition"], x["year"])),
                "source_year_conflicts": conflicted,
                "measurement": "gross direct deliveries to foreign final demand",
                "not_equivalent_to_oecd_tiva_ffd_dva": True}
    if name == "marxian_rates":
        from ..marxian_sectors import marxian_rates
        return marxian_rates(Path(evidence_root))
    raise KeyError(name)
