"""Read-only discovery of exact OECD STAN 2025 MEASURE codes from SDMX structure.

Publisher metadata is not itself proof that an individual country/period
contains observations. Never infer numeric values or amend archived responses.
"""
from __future__ import annotations

from hashlib import sha256
import xml.etree.ElementTree as ET

from .stan_originals import STAN_FLOW

MAX_STRUCTURE_BYTES = 20_000_000
STRUCTURE_URL = ("https://sdmx.oecd.org/public/rest/dataflow/"
                 "OECD.STI.PIE/DSD_STAN@DF_STAN_2025/1.0")
STRUCTURE_PARAMS = {"references": "all"}
STRUCTURE_ACCEPT = "application/vnd.sdmx.structure+xml;version=2.1"


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def parse_stan_measure_structure(raw: bytes) -> dict:
    """Extract the exact referenced MEASURE codelist from SDMX-ML metadata.

    Fail closed when the dataflow, measure dimension or codelist is absent.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_STRUCTURE_BYTES:
        raise ValueError("invalid_stan_structure_response_size")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("invalid_stan_structure_xml") from exc
    flows = [x for x in root.iter() if local_name(x) == "Dataflow"
             and x.get("id") == "DSD_STAN@DF_STAN_2025"
             and x.get("agencyID") == "OECD.STI.PIE"]
    if len(flows) != 1:
        raise ValueError("publisher_stan_2025_dataflow_missing_or_ambiguous")
    dimensions = [x for x in root.iter()
                  if local_name(x) in ("Dimension", "MeasureDimension")
                  and x.get("id") == "MEASURE"]
    if len(dimensions) != 1:
        raise ValueError("publisher_measure_dimension_missing_or_ambiguous")
    dimension_refs = [x.get("id") for x in dimensions[0].iter()
                      if local_name(x) == "Ref" and x.get("id")]
    if len(dimension_refs) != 1:
        raise ValueError("publisher_measure_codelist_ref_missing_or_ambiguous")
    candidates = [x for x in root.iter()
                  if local_name(x) == "Codelist"
                  and x.get("id") == dimension_refs[0]]
    if len(candidates) != 1:
        raise ValueError("publisher_measure_codelist_missing_or_ambiguous")
    codelist = candidates[0]
    measures = []
    for code in codelist:
        if local_name(code) != "Code":
            continue
        code_id = code.get("id")
        names = [n for n in code if local_name(n) == "Name"]
        english = next(
            (n.text or "" for n in names
             if n.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"), None)
        label = english if english is not None else (
            (names[0].text or "") if names else "")
        if not code_id:
            raise ValueError("publisher_measure_code_without_id")
        measures.append({"id": code_id, "label": label})
    if not measures or len({m["id"] for m in measures}) != len(measures):
        raise ValueError("publisher_measure_code_set_invalid")
    income = [m for m in measures
              if "surplus" in m["label"].lower() or "mixed income" in m["label"].lower()]
    return {
        "dataflow": STAN_FLOW,
        "measure_codelist_id": codelist.get("id"),
        "codelist_agency": codelist.get("agencyID"),
        "measure_code_count": len(measures),
        "surplus_measures": income,
        "historical_candidates_present": [
            m["id"] for m in measures
            if m["id"] in ("B2N_B3_N", "B2N_B3N", "B2G_B3G", "B2N", "B2G")
        ],
        "source_sha256": sha256(raw).hexdigest(),
        "publisher_values_acquired": False,
        "country_coverage_verified": False,
    }
