"""L04 framework originals: pinned bytes, Table A1 replication and the seven gates."""
from hashlib import md5, sha1, sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from test_euklems import workbook
from finance_dashboard import marxian_sectors as ms
from finance_dashboard.bis import ProviderError
from finance_dashboard.marxian_acceptance import marxian_role_checks
from finance_dashboard.source_policy import SourcePolicyGate, managed_client
from finance_dashboard.source_policy_registry import PolicyRegistry

YEARS = (2000, 2001)
COUNTRIES = ("AAA", "BBB")
PA = ["A01", "C10-C12", "E37-E39", "M71", "M72", "M74_M75"]
UA = {"Finance": ["K64"], "Real Estate": ["L68"], "Government": ["O84"], "Trade": ["G46"], "Additional": ["N"]}
EX = ["T"]
VARIABLES = ms.LEVELS


def tables():
    activities = [["Table A1", "", ""], ["code", "row", "Productive Activities"]]
    row = 1.0
    for code in PA:
        activities.append([code, row, code]); row += 1
    for label, codes in UA.items():
        activities.append(["", "", f"Unproductive Activities ({label})"])
        for code in codes:
            activities.append([code, row, code]); row += 1
    activities.append(["", "", "Excluded Activities"])
    for code in EX:
        activities.append([code, row, code]); row += 1
    return workbook({"List of Countries": [["Table 1", "", "", ""], [COUNTRIES[0], "A", COUNTRIES[1], "B"], ["ROW", "Rest", "", ""]],
                     "Activities (complete)": activities})


def value(country, variable, code, year):
    """A distinct exact binary fraction per cell, so sums are exactly reproducible."""
    return float(1 + COUNTRIES.index(country) * 7 + VARIABLES.index(variable) * 3
                 + (PA + sum(UA.values(), []) + EX).index(code) + (year - 2000) * 0.5)


def sea():
    codes = PA + sum(UA.values(), []) + EX
    data = [["country", "variable", "description", "code", *map(float, YEARS)]]
    for country in COUNTRIES:
        for variable in VARIABLES:
            for code in codes:
                data.append([country, variable, code, code, *[value(country, variable, code, y) for y in YEARS]])
    notes = [["WIOD Socio Economic Accounts"], ["Basic data"],
             ["Source: WIOD database  November 2016 release, published February 2018"], [], ["Countries", "Variables"],
             [], ["Acronym", "Name", "", "Values", "Description", ""]]
    notes += [[c, c, "", v, f"{v} (in millions of national currency)", ""] for c, v in zip(COUNTRIES * 5, VARIABLES)]
    return workbook({"Notes": notes, "DATA": data})


def panel(tamper=False):
    groups = {"PA": PA, "UA": sum(UA.values(), []), "UA.finance": UA["Finance"],
              "UA.realestate": UA["Real Estate"], "UA.gov": UA["Government"]}
    header = ["Country", "Year", "WIOT.TV.PA", "WIOT.VA.PA"] + [f"{v}.{g}" for v in VARIABLES for g in groups] + [
        "SEA.Rate.of.Surplus.Value.PA", "WIOT.SEA.Rate.of.Profit.over.K"]
    rows = [header]
    for country in COUNTRIES:
        for year in YEARS:
            levels = {(v, g): sum(value(country, v, code, year) for code in codes) for v in VARIABLES for g, codes in groups.items()}
            ratio = 0.75
            sv = (levels["VA", "PA"] - levels["COMP", "PA"]) / levels["COMP", "PA"]
            rk = (ratio * levels["GO", "PA"] - levels["COMP", "PA"]) / (levels["K", "PA"] + levels["K", "UA"])
            row = [country, float(year), 400.0, 300.0] + [levels[v, g] for v in VARIABLES for g in groups] + [sv, rk]
            rows.append(row)
    if tamper:
        rows[1][4] += 1.0
    return workbook({"Panel Data": rows})


def pdf(labels=None):
    lines = ["Table A1. Classification of Sectors", "Productive Activities Unproductive Activities",
             *(labels if labels is not None else ms.TP_PRODUCTIVE + ms.TP_UNPRODUCTIVE)]
    text = "BT /F1 8 Tf 20 800 Td 10 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               f"<< /Length {len(text)} >>\nstream\n{text}\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def originals(**overrides):
    files = {"rk-tables.xlsx": tables(), "rk-panel.xlsx": panel(), "tp-2017.pdf": pdf(), "wiod-sea.xlsx": sea()}
    files.update(overrides)
    return files


def pins(files):
    out = {}
    for name, raw in files.items():
        pin = {**ms.SOURCES[name], "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
        for key, function in (("md5", md5), ("sha1", sha1)):
            if key in pin:
                pin[key] = function(raw).hexdigest()
        out[name] = pin
    return out


class Fixture:
    def __init__(self, files):
        self.files = files
        self.patches = [patch.dict(ms.SOURCES, pins(files)), patch.object(ms, "YEARS", YEARS),
                        patch.object(ms, "COUNTRY_COUNT", len(COUNTRIES)),
                        patch.dict(ms.TABLE_A1_COUNTS, {"industries": len(PA) + 5 + len(EX), "PA": len(PA), "EX": len(EX)})]

    def __enter__(self):
        for item in self.patches:
            item.start()
        return self

    def __exit__(self, *exc):
        for item in reversed(self.patches):
            item.stop()


class MarxianSectorTests(unittest.TestCase):
    def test_pinned_originals_replicate_the_published_panel_and_roles_resolve_conditionally(self):
        files = originals()
        with TemporaryDirectory() as temp, Fixture(files):
            bundle = ms.store_marxian_sectors(files, Path(temp))
            self.assertEqual(ms.store_marxian_sectors(files, Path(temp)), bundle)
            evidence = ms.read_marxian_evidence(Path(temp))
        self.assertEqual(evidence["status"], "verified_framework_originals_replicated")
        replication = evidence["replication"]
        self.assertEqual(replication["level_checks"], replication["level_matches"])
        self.assertEqual(replication["level_checks"], len(COUNTRIES) * len(YEARS) * len(VARIABLES) * 5)
        self.assertEqual(replication["derived_matches"], len(COUNTRIES) * len(YEARS) * 2)
        alternative = evidence["classifications"]["tsoulfidis_paitaridis_2017_table_a1"]
        self.assertEqual(alternative["groups"]["PA"], len(PA) - 4)
        for role in ms_roles():
            result = marxian_role_checks(role, evidence)
            self.assertTrue(result["resolved"], role)
            self.assertTrue(result["conditional"], role)
            self.assertEqual([c["id"] for c in result["checks"]], [
                "source_binding", "native_dimensions", "stored_history", "original_source_values",
                "matched_periods", "publisher_dimensions", "temporal_evidence"])
        codes = {item["code"] for item in marxian_role_checks("productive_surplus_inputs", evidence)["checks"][-1]["limitations"]}
        self.assertLessEqual({"surplus_includes_depreciation", "io_input_origin_share_author_published"}, codes)

    def test_a_published_value_the_sea_does_not_reproduce_fails_the_values_gate(self):
        files = originals(**{"rk-panel.xlsx": panel(tamper=True)})
        with TemporaryDirectory() as temp, Fixture(files):
            ms.store_marxian_sectors(files, Path(temp))
            evidence = ms.read_marxian_evidence(Path(temp))
        self.assertEqual(evidence["status"], "framework_replication_failed")
        self.assertEqual(len(evidence["replication"]["mismatches"]), 1)
        gates = {c["id"]: c["state"] for c in marxian_role_checks("productive_labour_wages", evidence)["checks"]}
        self.assertEqual(gates["original_source_values"], "failed")

    def test_unpinned_or_changed_bytes_and_a_missing_alternative_label_are_rejected(self):
        files = originals()
        with TemporaryDirectory() as temp, Fixture(files):
            with self.assertRaises(ProviderError):
                ms.store_marxian_sectors({**files, "rk-tables.xlsx": files["rk-tables.xlsx"] + b"x"}, Path(temp))
            bundle = ms.store_marxian_sectors(files, Path(temp))
            (bundle / "wiod-sea.xlsx").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                ms.read_marxian_evidence(Path(temp))
        with self.assertRaises(ProviderError):
            ms.tp_classification(pdf(ms.TP_PRODUCTIVE), {code: "PA" for code in ms.TP_TO_UNPRODUCTIVE})

    def test_acquisition_fetches_only_the_pinned_publisher_urls_and_reads_the_owner_sea(self):
        files = originals()
        with TemporaryDirectory() as temp, Fixture(files):
            seen = []
            by_url = {ms.SOURCES[name]["url"]: raw for name, raw in files.items()}
            def respond(request):
                seen.append(str(request.url))
                return httpx.Response(200, content=by_url[str(request.url)])
            local = Path(temp) / "Socio_Economic_Accounts.xlsx"
            local.write_bytes(files["wiod-sea.xlsx"])
            now = [1_000_000.0]
            def sleep(seconds):
                now[0] += seconds
            gate = SourcePolicyGate(registry=PolicyRegistry(), state_path=Path(temp) / "policy.sqlite",
                                    clock=lambda: now[0], sleep=sleep)
            with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as client:
                ms.acquire_marxian_sectors(Path(temp) / "evidence", wiod_sea=local, client=client)
            evidence = ms.read_marxian_evidence(Path(temp) / "evidence")
        self.assertEqual(sorted(seen), sorted(ms.SOURCES[n]["url"] for n in ("rk-tables.xlsx", "rk-panel.xlsx", "tp-2017.pdf")))
        self.assertNotIn("dataverse.nl", " ".join(seen))
        self.assertEqual(evidence["status"], "verified_framework_originals_replicated")

    def test_reviewed_registration_route_imports_the_four_local_originals(self):
        from finance_dashboard.register_structured_original import register_structured
        files = originals()
        with TemporaryDirectory() as temp, Fixture(files):
            paths = {}
            for name, raw in files.items():
                paths[name] = Path(temp) / name
                paths[name].write_bytes(raw)
            result = register_structured("marxian_sectors", root=Path(temp) / "evidence", files=paths)
            with self.assertRaises(ValueError):
                register_structured("marxian_sectors", root=Path(temp) / "evidence",
                                    files={"wiod-sea.xlsx": paths["wiod-sea.xlsx"]})
        self.assertEqual(result["status"], "verified_framework_originals_replicated")

    def test_missing_originals_block_every_gate(self):
        with TemporaryDirectory() as temp:
            evidence = ms.read_marxian_evidence(Path(temp))
        self.assertFalse(evidence["original_source_hash_verified"])
        result = marxian_role_checks("capital_advance_inputs", evidence)
        self.assertEqual({c["state"] for c in result["checks"]}, {"blocked"})
        self.assertFalse(result["resolved"])

    def test_l04_resolves_conditionally_through_the_corpus(self):
        from finance_dashboard.catalog import load_documents
        from finance_dashboard.research_acceptance import analysis_acceptance
        from finance_dashboard.research_corpus import load_research_corpus
        l04 = next(a for a in load_research_corpus()["analyses"] if a["id"] == "L04")
        self.assertEqual(l04["phase2_scope"], "active")
        files = originals()
        with TemporaryDirectory() as temp, Fixture(files):
            ms.store_marxian_sectors(files, Path(temp))
            evidence = {"marxian_sectors": ms.read_marxian_evidence(Path(temp))}
        by_id = {row["id"]: row for row in load_documents()[0]["series"]}
        result = analysis_acceptance(l04, by_id, {}, [], observations_checked=True, artifact_evidence=evidence)
        self.assertEqual({r["role"]: r["state"] for r in result["requirements"]},
                         dict.fromkeys(ms_roles(), "accepted"))
        self.assertEqual(result["comparison"]["state"], "passed")
        self.assertEqual(result["state"], "conditional")
        blocked = analysis_acceptance(l04, by_id, {}, [], observations_checked=True, artifact_evidence={})
        self.assertNotIn(blocked["state"], ("accepted", "conditional"))


def ms_roles():
    return ("productive_labour_wages", "productive_surplus_inputs", "capital_advance_inputs", "industry_classification")


if __name__ == "__main__":
    unittest.main()
