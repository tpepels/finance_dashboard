"""Original OECD 2025 regular ICIO from identified, hash-pinned replicas.

Validate the complete Z, six final-demand categories, output, value added and
taxes. This is data accounting, not a Leontief model or historical acceptance.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from python_calamine import CalamineWorkbook

from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

PACKAGE_URL = "https://reproducibility.worldbank.org/catalog/511/download/1471/RR_WLD_2026_593.zip"
README_URL = "https://webfs-sti.oecd.org/files/STI-PIE/ICIO/2025/ReadMe_ICIO_small.xlsx"
CATALOGUE_URL = "https://reproducibility.worldbank.org/catalog/511"
MEMBER = "RR_WLD_2026_593/reproducibility_package/data_raw/2022_SML.csv"
PACKAGE_SHA256 = "de4011bc3205761b8622b7d1d67d1df80f09f892626d64d8a0e6b985e5a28bac"
README_SHA256 = "dec015b4d89190607fac90710352c9076d0c58ddfcdf6abf1fb6703d6cfca1ba"
MATRIX_SHA256 = "fbab8fd2727bda9fd8c6cfee8227816db82d33bef6aa4b90194ca5dcbc5ad14b"
IDENTITY = {"publisher": "OECD", "edition": "2025", "update": "January 2026",
            "table": "regular", "year": 2022, "replica": "RR_WLD_2026_593"}
HISTORY_REPLICA = "aditya1240/liberation-day-data"
HISTORY_REVISION = "9376a67717c1ab5f1ba24379ce5ea8669b72eacb"
HISTORY_ROOT = f"https://huggingface.co/datasets/{HISTORY_REPLICA}/resolve/{HISTORY_REVISION}/data/OECD_ICIO_SML_2016_2022"
# Public LFS content hashes, checked against every retained original. The 2022
# member is also independently identical to the World Bank package above.
# A mirror's MIT repository card does not change the OECD matrix's rights.
EARLY_PACKAGE_URL = "https://reproducibility.worldbank.org/catalog/601/download/1785/RR_THA_2026_689.zip"
EARLY_PACKAGE_SHA256 = "355736eb81a887e6900cb03699700259b9ce678f32b4c3618e0b5a7250b584b4"
EARLY_MEMBER_ROOT = "RR_THA_2026_689/reproducibility_package/simulations/tiva_2025/tiva_raw_2025"
# These originals are explicitly a different, replica-documented release.
# The older balanced 2022 matrix is for release comparison only: it must not
# replace the retained January-2026 matrix or erase that original's failures.
OCTOBER_2025_MATRICES = {
    1995: {"sha256": "4ed63b49ff1452a5dc0834f0ad971b4d266c804345bc07b3e0fb6e7f5800dda2", "bytes": 75555276},
    2022: {"sha256": "e006e57f9bc3c44bd938f0e86a8a5193f156184851fa94b2dee82cc5248a99d1", "bytes": 88412091},
}
HISTORY_MATRICES = {
    1995: {**OCTOBER_2025_MATRICES[1995], "source_url": EARLY_PACKAGE_URL,
           "replica": "RR_THA_2026_689", "replica_declared_update": "October 2025",
           "package_sha256": EARLY_PACKAGE_SHA256, "archive_member": f"{EARLY_MEMBER_ROOT}/1995_SML.csv"},
    2016: {"sha256": "de91a560b3f4b1c75ab18846da13418d663844b465724691598a4e39bf5a09c2", "bytes": 86745061},
    2017: {"sha256": "07a07dc53f1302a35c984f2801a98899ea3e73c9704e8350cbb36587200a4b19", "bytes": 87440646},
    2018: {"sha256": "3d14b8d34c5cc036fd2eb91fc44edce97c904ea8657cc273a162de84153ae23b", "bytes": 87878366},
    2019: {"sha256": "85bd13fd8c2385c41d239d2ddc973ced1caa87c59c2b90b7bed3ff97048043d8", "bytes": 88008102},
    2020: {"sha256": "92955212d9c8942112b7cc9b9251e55dd841e5a607376580a20d37fc54eb20a9", "bytes": 87356600},
    2021: {"sha256": "9a5c161ff1625e841c5901218adcdba0a81b3ee5872c2180ba2cbbabfcba4694", "bytes": 88793390},
    2022: {"sha256": MATRIX_SHA256, "bytes": 90120552},
}
# Publisher-direct OECD 2025 regular archives (January 2026 update), downloaded
# by the owner in a browser from the OECD ICIO page; the automated route is a
# Cloudflare challenge. Archive and member bytes are pinned on receipt.
PUBLISHER_ARCHIVES = {
    "1995-2000_SML.zip": {"sha256": "3bfd5cb014bf3436e3435ad50c0e6b66039ad2f6c484e6e26fad0bc92ef4725b", "bytes": 110135258},
    "2001-2005_SML.zip": {"sha256": "75015a66e7944e7377a5a08a02155a472517efe4e4a36b1116c7542f759f78f6", "bytes": 99391392},
    "2006-2010_SML.zip": {"sha256": "e57685c00ad30b4353e1e7de24910ba70b181c5198c9dbb6d46eb349de76f35a", "bytes": 111587430},
    "2011-2015_SML.zip": {"sha256": "d9025195bdb9a03278ba6403066cef2969cc30185a1b28117c9452994a203619", "bytes": 116134326},
    "2016-2022_SML.zip": {"sha256": "46db55c45747e26dde5c1716d072b2aa74ace362a4424491ac646d2ab175befb", "bytes": 166241019},
}
PUBLISHER_MATRICES = {
    1995: {"archive": "1995-2000_SML.zip", "member": "1995_SML.csv", "sha256": "aaf97e2b119b799be4a9a0fa510b77ac351f9810b1bee8f19468cf210603ae8d", "bytes": 76702208},
    1996: {"archive": "1995-2000_SML.zip", "member": "1996_SML.csv", "sha256": "f6dc28604889f04e4399f9d66a483a6a9fb2db7d0aafb782fcaa579a2d65674a", "bytes": 78153862},
    1997: {"archive": "1995-2000_SML.zip", "member": "1997_SML.csv", "sha256": "26d596ce232c69e2b6ae1f842d45e9305e35f8db152e02f0a93a948dc1191277", "bytes": 78606048},
    1998: {"archive": "1995-2000_SML.zip", "member": "1998_SML.csv", "sha256": "2913a4080bfe0f3905beef5ee5e40896cad5bc6b82a79bf1b4a8b0a5358b13a6", "bytes": 78790602},
    1999: {"archive": "1995-2000_SML.zip", "member": "1999_SML.csv", "sha256": "14a20790452855fcd82ae2a1f0a675106eea2392be7b0113487f7a234dc2328a", "bytes": 79033507},
    2000: {"archive": "1995-2000_SML.zip", "member": "2000_SML.csv", "sha256": "1e0c554591ef867591ed37e8c93731d5d26eeea6f11926c6d52230f5674ddba7", "bytes": 79079811},
    2001: {"archive": "2001-2005_SML.zip", "member": "2001_SML.csv", "sha256": "1ca99acbe8314df5356bb249dfebc5ed391d2230039075837202b5c6a0651c89", "bytes": 79654589},
    2002: {"archive": "2001-2005_SML.zip", "member": "2002_SML.csv", "sha256": "00e15335c777406b9a0d78730eb5ee16b5c4e20e3b202cb049fcf295aa1e01a0", "bytes": 80353202},
    2003: {"archive": "2001-2005_SML.zip", "member": "2003_SML.csv", "sha256": "9ab0494258eeb994f7b1997e40dd5235fd83157f9f7ec10bb697e6214b35063a", "bytes": 81134227},
    2004: {"archive": "2001-2005_SML.zip", "member": "2004_SML.csv", "sha256": "5c00567fdc62bd1889271c41267090ca4b7ab7d4119eeeefac658491bc70e03b", "bytes": 82171405},
    2005: {"archive": "2001-2005_SML.zip", "member": "2005_SML.csv", "sha256": "41faa9731e12bdd46aa3a498897e57678e430bdbac6038e4e7e3729aa9d38405", "bytes": 83228380},
    2006: {"archive": "2006-2010_SML.zip", "member": "2006_SML.csv", "sha256": "4b43380a4d7491ae2a0562dc940f5310a5cffcaed85cc4509b1df061ff661c65", "bytes": 84242864},
    2007: {"archive": "2006-2010_SML.zip", "member": "2007_SML.csv", "sha256": "e61f9c95a5b3fafef1f67718d6977c718bb09835474f13e345208998fdc3f648", "bytes": 85468143},
    2008: {"archive": "2006-2010_SML.zip", "member": "2008_SML.csv", "sha256": "2dcc5459559cf7a540e38b367c4ab2d8640067ea9a1d3b1763d3ba152817d86e", "bytes": 86613819},
    2009: {"archive": "2006-2010_SML.zip", "member": "2009_SML.csv", "sha256": "b8cdef5d7df937a9f2038e8a0127140406c7a8a911d026e1a243f86a95a217fe", "bytes": 85488193},
    2010: {"archive": "2006-2010_SML.zip", "member": "2010_SML.csv", "sha256": "7c81520b2e419e8c0f5938668962a486ba7d7d67d617db24199c6eb1b1797ad9", "bytes": 86069015},
    2011: {"archive": "2011-2015_SML.zip", "member": "2011_SML.csv", "sha256": "373da85dd3004ea937098189d3635628045403132a5c678d8eedab058c3d4624", "bytes": 87055769},
    2012: {"archive": "2011-2015_SML.zip", "member": "2012_SML.csv", "sha256": "e88dfd5e9571dc61afefcb998fdf85703e6acb59f61d9f8c5e2545ffdea3d16e", "bytes": 86802969},
    2013: {"archive": "2011-2015_SML.zip", "member": "2013_SML.csv", "sha256": "584e1f9b47b5812cda6fd7d09c3efa363397141089382dc034f991f733530cc7", "bytes": 87189902},
    2014: {"archive": "2011-2015_SML.zip", "member": "2014_SML.csv", "sha256": "c2f922baa5e0b34fa8a974415bb10cdc7e5661cb2a61f645d343e7bea665da08", "bytes": 87379891},
    2015: {"archive": "2011-2015_SML.zip", "member": "2015_SML.csv", "sha256": "7bb94ddc61bab5458017f1c6d1c3449f2d16e93d3d09a6d8acb5bce88d3734c3", "bytes": 86722828},
    2016: {"archive": "2016-2022_SML.zip", "member": "2016_SML.csv", "sha256": "de91a560b3f4b1c75ab18846da13418d663844b465724691598a4e39bf5a09c2", "bytes": 86745061},
    2017: {"archive": "2016-2022_SML.zip", "member": "2017_SML.csv", "sha256": "07a07dc53f1302a35c984f2801a98899ea3e73c9704e8350cbb36587200a4b19", "bytes": 87440646},
    2018: {"archive": "2016-2022_SML.zip", "member": "2018_SML.csv", "sha256": "3d14b8d34c5cc036fd2eb91fc44edce97c904ea8657cc273a162de84153ae23b", "bytes": 87878366},
    2019: {"archive": "2016-2022_SML.zip", "member": "2019_SML.csv", "sha256": "85bd13fd8c2385c41d239d2ddc973ced1caa87c59c2b90b7bed3ff97048043d8", "bytes": 88008102},
    2020: {"archive": "2016-2022_SML.zip", "member": "2020_SML.csv", "sha256": "92955212d9c8942112b7cc9b9251e55dd841e5a607376580a20d37fc54eb20a9", "bytes": 87356600},
    2021: {"archive": "2016-2022_SML.zip", "member": "2021_SML.csv", "sha256": "9a5c161ff1625e841c5901218adcdba0a81b3ee5872c2180ba2cbbabfcba4694", "bytes": 88793390},
    2022: {"archive": "2016-2022_SML.zip", "member": "2022_SML.csv", "sha256": "fbab8fd2727bda9fd8c6cfee8227816db82d33bef6aa4b90194ca5dcbc5ad14b", "bytes": 90120552},
}
# Independently reproduced audit outputs for these exact original/ReadMe pairs.
# A reader verifies original bytes, immutable receipts and this code-pinned
# result; acquisition/explicit diagnostics still run the complete accounting.
# This avoids redoing 130 million Decimal cell operations on a cold API read.
PINNED_AUDITS = {
    (MATRIX_SHA256, README_SHA256, 2022, "regular-package-accounting-v1"):
        "38aa8ccf7a12a0d512b6e2022c543da425336762918adf0538905eab4c48bdcb",
    **{(HISTORY_MATRICES[year]["sha256"], README_SHA256, year, "regular-history-accounting-v1"): digest
       for year, digest in {
           1995: "9d62b90c841d62dce779a4a43d84d55b121e6e607515b09262319c3936b816eb",
           2016: "8492820482ad5aafdda3bfadc8ef57f98d2144c4fac2f252bbdcee486b11d4dc",
           2017: "61d03fffd73cc632b59916a1aa928495f5acccad473dfed93c6c05226ca4cd16",
           2018: "f21fa962139464e41a596f93da42bc5aa492f93aa11fca6f561a20ad7cff1ee6",
           2019: "e49cdb2daad88efb59c3404ae75868c9f394a133edc4701d3181470f06ef3582",
           2020: "ccacf1c0e9541cb930d62a4f2ca7e49e65cc4a6dd1784e8dcb265bc85c036e96",
           2021: "702fcaf719a95aafe5fa8ca1480c936d15b87d485d671f9b283eb2702f5ccf51",
           2022: "144a796c4938b77f408497b6e5f99e67b2df8e59ed75cc35c4d4cce640857bb9",
       }.items()},
    # Publisher-direct January 2026 members, each audited in full on receipt.
    **{(PUBLISHER_MATRICES[year]["sha256"], README_SHA256, year, "regular-publisher-accounting-v1"): digest
       for year, digest in {
           1995: "c7fba6b18eac57084769a03fbd056aec8dde0f46d41b15930a36cb9854f4b346",
           1996: "a7d098c345122da25da34badf9ce17a801f548e1249197ec5df6fe5f93c4f4dd",
           1997: "9e35118487cd507b850038d23b624ae98ebe129d842c62ad63472f28dad260f8",
           1998: "423b1bf404fac762316690c2002c628fcb5023e448d532c8271108201c268005",
           1999: "c8394e9353f2bb86437d4699072f0912f18fbb92fc538311d6b519b520a3cccd",
           2000: "039914b9187f865f64fbb09b5e3d0ac47db8d0e31a5ba4ccd4e8f85dd8455dfc",
           2001: "f5170da7298a040554cc79b911ad16360933eca1918f8bac6540858aa7734f2f",
           2002: "8b033d4eb83784ccfed4dcafa7de7fcc11f565a09714aa0fb5cc3ec7d1bbddea",
           2003: "e25f583cc2d6edfccc1d14f6e1ee55b893f248ab1ed95621c1b38d187d01167e",
           2004: "853b47c0179bcfea166f4aa18cc632b719f1a2487f9b7e66143ce9a9ecfb7aca",
           2005: "b6c417cbbf88cdf800b84b6a392623f8da9073bc668479fbc56e48c0c029a2cd",
           2006: "98ed4ee32dc14979b889a13de1b803cd04da1c9fedc7096f8f6859c489e49b79",
           2007: "6208d20817dd3aae802b24d8469e936012aeb3d8ce05c18bab3e33ef6f071484",
           2008: "40e0314fe681d2acaf2325cc5210ac425210a74b25befc5b24e25f8ccd61837a",
           2009: "0adf49d0db253a5fe259ef225bf8e99197963ab3ed5f02fcf231a1981f189b5b",
           2010: "3a29f53b4de6f63e4b9e2b3bd455a3af7d3a0330ee80303a4d2cc31b3e0e66d7",
           2011: "53c49087912b294cdeb2634af5311a06e3d5cb1b12925168c5079f8a0cedc690",
           2012: "7244ef1cfbfdbb54250d7596d5d0105d7cb2ab2f2e41c18034db24fa621c62b4",
           2013: "d628da6bb9def8d5e6cbdf5f30854d47a42b716659cae5a4cf3b423438d9beb7",
           2014: "e282396caf58c7ca91d5661c8789fbbfc66613631acab6eed55bb7b037c87ff6",
           2015: "33aed7ce4dc417e7bb97f35adcca364d5dada8d29d324208344e1f5cd685d92b",
           2016: "f85fe83b6d64814b902432f5b2bc53774cdd4fc37a74d020b4af1e59a7376944",
           2017: "b351b08d58b329b79064267fa794d385c45615a287a50901e647f5878e59563b",
           2018: "9e75bee594ace559c22d212eeee11cae700d47db68d7ddc1fff5d788e4a8a1f4",
           2019: "20b3fc3134aacf59264e9450b4d0bddbdb97f98fc94341409fd4d3417197d999",
           2020: "b2c4b24b457b9b2b890edd6abd5ab34f83b9c21e025066b9333cf5995a7f0afa",
           2021: "494724ce00daf14e0ccd748583aa1e5e6994e099b26fe8bc6572cd08a6e9d5d3",
           2022: "218cff0d38d31415fb1b31d4b5712bc85aefcb37f208987aed9c56e582f5ea34",
       }.items()},
}


def _history_identity(year):
    if year not in HISTORY_MATRICES:
        raise ValueError("icio_unregistered_original_year")
    descriptor = HISTORY_MATRICES[year]
    if "archive_member" in descriptor:
        return {"publisher": "OECD", "edition": "2025", "table": "regular", "year": year,
                "replica": descriptor["replica"], "replica_declared_update": descriptor["replica_declared_update"],
                "replica_package_sha256": descriptor["package_sha256"]}
    return {"publisher": "OECD", "edition": "2025", "table": "regular", "year": year,
            "replica": HISTORY_REPLICA, "replica_revision": HISTORY_REVISION}


def _history_source_url(year):
    return HISTORY_MATRICES[year].get("source_url", f"{HISTORY_ROOT}/{year}_SML.csv")


def _hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readme_dimensions(raw: bytes) -> dict:
    if sha256(raw).hexdigest() != README_SHA256:
        raise ValueError("icio_readme_identity_mismatch")
    workbook = CalamineWorkbook.from_filelike(io.BytesIO(raw))
    text = " ".join(str(cell) for row in workbook.get_sheet_by_name("ReadMe").to_python() for cell in row)
    if "2025 edition" not in text or "Data are expressed in current USD, million" not in text:
        raise ValueError("icio_unit_or_edition_mismatch")
    def codes(sheet):
        # Published numeric item labels have some numbering errors. Source
        # codes and their actual ordering, not those labels, define dimensions.
        return [str(row[1]) for row in workbook.get_sheet_by_name(sheet).to_python()
                if isinstance(row[0], (int, float))]
    rows, columns = codes("RowItems"), codes("ColItems")
    industries = rows[:-3]
    final = columns[len(industries):-1]
    countries = list(dict.fromkeys(code.split("_", 1)[0] for code in industries))
    sectors = list(dict.fromkeys(code.split("_", 1)[1] for code in industries))
    if (rows[-3:] != ["TLS", "VA", "OUT"] or columns[-1] != "OUT"
            or columns[:len(industries)] != industries or len(rows) != 4053 or len(columns) != 4537
            or len(set(rows)) != len(rows) or len(set(columns)) != len(columns)
            or len(countries) != 81 or len(sectors) != 50
            or industries != [f"{area}_{sector}" for area in countries for sector in sectors]
            or final != [f"{area}_{category}" for area in countries
                         for category in ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DPABR")]):
        raise ValueError("icio_readme_dimensions_invalid")
    return {"industry_codes": industries, "final_demand_codes": final, "unit": "current_USD_million",
            "country_count": len(countries), "industry_count": len(sectors)}


def audit_matrix(stream, industry_codes: list[str], final_demand_codes: list[str], *,
                 include_residuals: bool = False) -> dict:
    n, f = len(industry_codes), len(final_demand_codes)
    expected = industry_codes + ["TLS", "VA", "OUT"]
    if not n or len(set(expected)) != len(expected):
        raise ValueError("icio_dimensions_invalid")
    reader = csv.reader(stream)
    if next(reader, None) != ["V1", *industry_codes, *final_demand_codes, "OUT"]:
        raise ValueError("icio_header_mismatch")
    column_sums = [Decimal(0)] * n
    outputs, zero_output, negatives, source_scale = [], [], 0, 0
    row_failures, row_residuals, specials = [], [], {}
    row_details, column_details = [], []
    signed_row_total = signed_column_total = Decimal(0)
    totals = {"intermediate_use": Decimal(0), "final_demand": Decimal(0), "gross_output": Decimal(0)}
    countries = {}
    for index, row in enumerate(reader):
        if index >= len(expected) or len(row) != n + f + 2 or row[0] != expected[index]:
            raise ValueError("icio_row_identity_or_width_invalid")
        try:
            values = [Decimal(cell) for cell in row[1:]]
            if any(not value.is_finite() for value in values):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ValueError("icio_numeric_value_invalid") from None
        negatives += sum(value < 0 for value in values)
        source_scale = max(source_scale, max(-value.as_tuple().exponent for value in values))
        if source_scale > 4:
            raise ValueError("icio_unexpected_source_precision")
        if index < n:
            intermediate = sum(values[:n], Decimal(0))
            final = sum(values[n:n + f], Decimal(0))
            output = values[-1]
            if output < 0:
                raise ValueError("icio_negative_gross_output")
            if output == 0:
                zero_output.append(row[0])
            outputs.append(output)
            for col, value in enumerate(values[:n]):
                column_sums[col] += value
            residual = intermediate + final - output
            signed_row_total += residual
            row_residuals.append(abs(residual))
            # Rounding bound for n+f independently serialized 4dp cells and
            # output. This is finite-precision accounting, not uncertainty.
            if abs(residual) > Decimal("0.00005") * (n + f + 1):
                row_failures.append(row[0])
                row_details.append({"code": row[0], "residual": str(residual), "gross_output": str(output)})
            totals["intermediate_use"] += intermediate
            totals["final_demand"] += final
            totals["gross_output"] += output
            area = row[0].split("_", 1)[0]
            country = countries.setdefault(area, {key: Decimal(0) for key in totals})
            for key, value in (("intermediate_use", intermediate), ("final_demand", final), ("gross_output", output)):
                country[key] += value
        else:
            specials[row[0]] = values
    if set(specials) != {"TLS", "VA", "OUT"} or len(outputs) != n:
        raise ValueError("icio_incomplete_matrix")
    column_failures, output_failures, residuals = [], [], []
    for index, code in enumerate(industry_codes):
        residual = column_sums[index] + specials["TLS"][index] + specials["VA"][index] - specials["OUT"][index]
        signed_column_total += residual
        residuals.append(abs(residual))
        if abs(residual) > Decimal("0.00005") * (n + 3):
            column_failures.append(code)
            column_details.append({"code": code, "residual": str(residual),
                                   "gross_output": str(specials["OUT"][index])})
        if outputs[index] != specials["OUT"][index]:
            output_failures.append(code)
        country = countries[code.split("_", 1)[0]]
        for name, source in (("value_added", "VA"), ("taxes_less_subsidies", "TLS")):
            country[name] = country.get(name, Decimal(0)) + specials[source][index]
    def strings(value):
        if isinstance(value, Decimal): return str(value)
        if isinstance(value, dict): return {key: strings(item) for key, item in value.items()}
        return value
    report = {"audit_method_version": 1, "industry_cells": n * n, "final_demand_cells": n * f,
        "industry_nodes": n, "final_demand_columns": f, "negative_cells": negatives,
        "source_decimal_places": source_scale, "zero_output_nodes": zero_output,
        "identities": {"outputs": "row_sum(Z)+row_sum(F)=OUT",
                       "inputs_plus_taxes_plus_value_added": "column_sum(Z)+TLS+VA=OUT",
                       "rounding_quantum_current_USD_million": "0.0001",
                       "row_rounding_bound": str(Decimal("0.00005") * (n + f + 1)),
                       "column_rounding_bound": str(Decimal("0.00005") * (n + 3))},
        "maximum_row_residual": str(max(row_residuals)), "maximum_column_residual": str(max(residuals)),
        "row_accounting_failures": row_failures, "column_accounting_failures": column_failures,
        "output_vector_mismatches": output_failures,
        "accounting_passed": not (row_failures or column_failures or output_failures),
        "global_totals": strings(totals), "countries": strings(countries)}
    if include_residuals:
        def counts(entries, dimension):
            result = {}
            for entry in entries:
                key = entry["code"].split("_", 1)[dimension]
                result[key] = result.get(key, 0) + 1
            return dict(sorted(result.items()))
        # Opt-in investigation details leave the archived version-1 audit
        # byte-reproducible. Localization does not establish a source cause.
        report["residual_diagnostics"] = {
            "schema_version": 1, "cause_status": "unexplained_original_source_residuals",
            "sign_convention": "sum_of_inputs_or_uses_minus_published_output",
            "signed_row_residual_total": str(signed_row_total),
            "signed_column_residual_total": str(signed_column_total),
            "rows": sorted(row_details, key=lambda item: (-abs(Decimal(item["residual"])), item["code"])),
            "columns": sorted(column_details, key=lambda item: (-abs(Decimal(item["residual"])), item["code"])),
            "row_failure_counts_by_country": counts(row_details, 0),
            "row_failure_counts_by_industry": counts(row_details, 1),
            "column_failure_counts_by_country": counts(column_details, 0),
            "column_failure_counts_by_industry": counts(column_details, 1),
        }
    return report


@lru_cache(maxsize=4)
def _pinned_audit(package_path: str, readme_path: str, include_residuals: bool = False) -> dict:
    # Callers rehash original files before using this immutable-content cache.
    dimensions = readme_dimensions(Path(readme_path).read_bytes())
    with zipfile.ZipFile(package_path) as archive:
        if archive.namelist().count(MEMBER) != 1 or archive.getinfo(MEMBER).file_size > 100_000_000:
            raise ValueError("icio_archive_member_invalid")
        raw = archive.read(MEMBER)
        ledger = archive.read("RR_WLD_2026_593/data_hash_report.csv").decode("utf-8")
        if sha256(raw).hexdigest() != MATRIX_SHA256 or f"2022_SML.csv,2022_SML.csv,{MATRIX_SHA256}," not in ledger:
            raise ValueError("icio_original_matrix_hash_mismatch")
    with io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig") as stream:
        audit = audit_matrix(stream, dimensions["industry_codes"], dimensions["final_demand_codes"],
                             include_residuals=include_residuals)
    return {**audit, **IDENTITY, "country_count": dimensions["country_count"],
        "industry_count": dimensions["industry_count"], "unit": dimensions["unit"],
        "matrix_sha256": MATRIX_SHA256, "readme_sha256": README_SHA256,
        "package_sha256": PACKAGE_SHA256, "matrix_archive_member": MEMBER,
        "full_history_verified": False, "first_publication_verified": False,
        "rights": "OECD matrix CC BY 4.0 as documented by the World Bank catalogue; other package inputs have separate rights",
        "citation": "OECD (2025), OECD Inter-Country Input-Output Tables, January 2026 regular update; World Bank replication RR_WLD_2026_593",
        "source_url": CATALOGUE_URL,
        "limitations": ["2022 cross-section only; 1995–2021 matrices remain absent.",
            "Original matrix supplied by an identified replica, not publisher-direct ZIP bytes.",
            "Source accounting residuals above serialization rounding are retained and block a balanced-matrix claim; no cells are adjusted.",
            "Zero-output nodes require explicit treatment before forming technical coefficients.",
            "No Leontief inverse, causal shock or whole G06 scientific acceptance is claimed."]}


def _verify_pins(package, readme):
    if (Path(package).is_symlink() or Path(readme).is_symlink()
            or _hash(package) != PACKAGE_SHA256 or _hash(readme) != README_SHA256):
        raise ValueError("icio_pinned_original_identity_mismatch")


def diagnose_icio_package(package: Path, readme: Path) -> dict:
    """Read-only signed residual investigation, separate from archived audits."""
    _verify_pins(package, readme)
    return _pinned_audit(str(package.resolve()), str(readme.resolve()), True)


def store_icio_package(package: Path, readme: Path, evidence_root: Path) -> Path:
    _verify_pins(package, readme)
    audit = _pinned_audit(str(package.resolve()), str(readme.resolve()))
    return _store_original_bundle(Path(evidence_root) / "icio" / "regular-2025-2022",
        {"package.zip": Path(package), "readme.xlsx": Path(readme)}, audit, IDENTITY,
        {"package": PACKAGE_URL, "readme": README_URL}, _verify_icio_bundle)


def _store_original_bundle(parent, originals, audit, identity, sources, verify):
    """One atomic original/audit/receipt boundary for both ICIO replica formats."""
    # Preserve the exact publisher-replica bytes even when their accounting
    # fails. Acquisition is evidence, never permission to silently rebalance.
    payload = canonical_bytes(audit)
    files = {name: _hash(path) for name, path in originals.items()}
    files["audit.json"] = sha256(payload).hexdigest()
    digest = sha256(canonical_bytes(files)).hexdigest()
    parent.mkdir(parents=True, exist_ok=True)
    bundle, temporary = parent / digest, None
    try:
        if not bundle.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".icio-", dir=parent))
            for name, path in originals.items():
                shutil.copyfile(path, temporary / name)
            (temporary / "audit.json").write_bytes(payload)
            (temporary / "manifest.json").write_bytes(canonical_bytes({"schema_version": 1,
                "source_identity": identity, "files": files, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "sources": sources, "matrix_sha256": audit["matrix_sha256"]}))
            os.rename(temporary, bundle)
            temporary = None
        verify(bundle)
        record_acquisition_receipt(bundle, identity)
        return bundle
    finally:
        if temporary is not None: shutil.rmtree(temporary)


def _verified_manifest(bundle, identity, names, sources, matrix_hash):
    if bundle.is_symlink() or (bundle / "manifest.json").is_symlink():
        raise ValueError("icio_archive_identity_invalid")
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    files = manifest["files"]
    if (manifest.get("schema_version") != 1 or manifest.get("source_identity") != identity
            or set(files) != names or manifest.get("sources") != sources
            or manifest.get("matrix_sha256") != matrix_hash
            or sha256(canonical_bytes(files)).hexdigest() != bundle.name):
        raise ValueError("icio_archive_identity_invalid")
    for name, digest in files.items():
        if (bundle / name).is_symlink() or _hash(bundle / name) != digest:
            raise ValueError("icio_archive_hash_mismatch")
    return manifest


def _verify_icio_bundle(bundle):
    manifest = _verified_manifest(bundle, IDENTITY, {"package.zip", "readme.xlsx", "audit.json"},
                       {"package": PACKAGE_URL, "readme": README_URL}, MATRIX_SHA256)
    if manifest["files"]["package.zip"] != PACKAGE_SHA256 or manifest["files"]["readme.xlsx"] != README_SHA256:
        raise ValueError("icio_pinned_original_identity_mismatch")
    audit = json.loads((bundle / "audit.json").read_bytes())
    _verify_audit_pin(audit, MATRIX_SHA256, 2022, "regular-package-accounting-v1")
    return audit


def _verify_audit_pin(audit, matrix_hash, year, method):
    expected = PINNED_AUDITS.get((matrix_hash, README_SHA256, year, method))
    if expected is None or sha256(canonical_bytes(audit)).hexdigest() != expected:
        raise ValueError("icio_archive_audit_mismatch")


def _verify_matrix_pins(matrix, readme, year):
    expected = HISTORY_MATRICES.get(year)
    if (expected is None or Path(matrix).is_symlink() or Path(readme).is_symlink()
            or Path(matrix).stat().st_size != expected["bytes"] or _hash(matrix) != expected["sha256"]
            or _hash(readme) != README_SHA256):
        raise ValueError("icio_pinned_original_identity_mismatch")


def _historical_audit(matrix_path: str, readme_path: str, year: int, original_hash: str) -> dict:
    """Run complete accounting during acquisition or explicit diagnostics."""
    dimensions = readme_dimensions(Path(readme_path).read_bytes())
    with Path(matrix_path).open(encoding="utf-8-sig", newline="") as stream:
        audit = audit_matrix(stream, dimensions["industry_codes"], dimensions["final_demand_codes"],
                             include_residuals=True)
    descriptor = HISTORY_MATRICES[year]
    provenance = ({"matrix_archive_member": descriptor["archive_member"],
                   "package_sha256": descriptor["package_sha256"]}
                  if "archive_member" in descriptor else {})
    return {**audit, **_history_identity(year), **provenance, "unit": dimensions["unit"],
            "country_count": dimensions["country_count"], "industry_count": dimensions["industry_count"],
            "matrix_sha256": original_hash, "readme_sha256": README_SHA256,
            "source_url": _history_source_url(year),
            "replica_content_hash_verified": True,
            "independent_replica_match_verified": year == 2022 and original_hash == MATRIX_SHA256,
            "publisher_direct_verified": False, "common_update_verified": False,
            "full_history_verified": False, "first_publication_verified": False,
            "rights": "OECD matrix CC BY 4.0; replica repository licence does not supersede OECD data rights",
            "limitations": ["Original regular-table bytes from a public replica; publisher-direct historical package remains unavailable.",
                "Matching ReadMe dimensions and replica content hashes do not independently establish the historical publisher update.",
                "The 2022 replica bytes independently match the World Bank ledger; earlier years lack that second source.",
                "Accounting failures, negative cells and zero-output nodes are retained without rebalancing.",
                "The regular table cannot reproduce extended-table TiVA exactly; no Leontief or shock result is certified."]}


def store_icio_matrix(matrix: Path, readme: Path, year: int, evidence_root: Path) -> Path:
    """Retain one pinned historical replica via the canonical ICIO evidence store."""
    _verify_matrix_pins(matrix, readme, year)
    audit = _historical_audit(str(matrix.resolve()), str(readme.resolve()), year, HISTORY_MATRICES[year]["sha256"])
    identity = _history_identity(year)
    return _store_original_bundle(Path(evidence_root) / "icio" / f"regular-2025-{year}-replica",
        {"matrix.csv": Path(matrix), "readme.xlsx": Path(readme)}, audit, identity,
        {"matrix": _history_source_url(year), "readme": README_URL},
        lambda bundle: _verify_historical_bundle(bundle, year))


def _verify_historical_bundle(bundle, year):
    matrix_hash = HISTORY_MATRICES[year]["sha256"]
    manifest = _verified_manifest(bundle, _history_identity(year), {"matrix.csv", "readme.xlsx", "audit.json"},
        {"matrix": _history_source_url(year), "readme": README_URL}, HISTORY_MATRICES[year]["sha256"])
    if manifest["files"]["matrix.csv"] != matrix_hash or manifest["files"]["readme.xlsx"] != README_SHA256:
        raise ValueError("icio_pinned_original_identity_mismatch")
    audit = json.loads((bundle / "audit.json").read_bytes())
    _verify_audit_pin(audit, matrix_hash, year, "regular-history-accounting-v1")
    return audit


PUBLISHER_AUDIT_METHOD = "regular-publisher-accounting-v1"
PUBLISHER_PAGE = "https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html"
# Publisher balancing tolerance: a residual above serialization rounding is
# immaterial when it stays within this share of the node's own gross output.
MATERIALITY_RELATIVE_TO_GROSS_OUTPUT = Decimal("0.001")


def material_accounting(audit: dict) -> dict:
    """Residuals relative to each failing node's own gross output; nothing is adjusted."""
    details = audit.get("residual_diagnostics")
    if audit.get("accounting_passed") is True:
        return {"material_accounting_passed": True, "residuals_above_rounding": 0}
    if not isinstance(details, dict) or audit.get("output_vector_mismatches"):
        return {"material_accounting_passed": False, "reason": "residual_detail_unavailable_or_output_mismatch"}
    def shares(items):
        out = []
        for item in items:
            output, residual = Decimal(item["gross_output"]), abs(Decimal(item["residual"]))
            out.append(residual / output if output > 0 else Decimal("Infinity"))
        return out
    rows, columns = shares(details["rows"]), shares(details["columns"])
    worst = max(rows + columns, default=Decimal(0))
    above = sum(share > MATERIALITY_RELATIVE_TO_GROSS_OUTPUT for share in rows + columns)
    return {"material_accounting_passed": above == 0,
            "bound_relative_to_node_gross_output": str(MATERIALITY_RELATIVE_TO_GROSS_OUTPUT),
            "residuals_above_rounding": len(rows) + len(columns),
            "residuals_above_materiality": above,
            "maximum_residual_share_of_node_gross_output": f"{worst:.3E}" if worst.is_finite() else "Infinity"}


def _publisher_identity(year):
    descriptor = PUBLISHER_MATRICES[year]
    return {"publisher": "OECD", "edition": "2025", "update": "January 2026", "table": "regular", "year": year,
            "acquisition": "owner_browser_download", "archive": descriptor["archive"],
            "archive_sha256": PUBLISHER_ARCHIVES[descriptor["archive"]]["sha256"]}


def _publisher_sources(year):
    archive = PUBLISHER_MATRICES[year]["archive"]
    return {"archive": f"{PUBLISHER_PAGE}#{archive}", "member": PUBLISHER_MATRICES[year]["member"], "readme": README_URL}


def _publisher_audit(matrix_path: str, readme_path: str, year: int) -> dict:
    dimensions = readme_dimensions(Path(readme_path).read_bytes())
    with Path(matrix_path).open(encoding="utf-8-sig", newline="") as stream:
        audit = audit_matrix(stream, dimensions["industry_codes"], dimensions["final_demand_codes"],
                             include_residuals=True)
    descriptor = PUBLISHER_MATRICES[year]
    replica = HISTORY_MATRICES.get(year, {}).get("sha256")
    return {**audit, **_publisher_identity(year), "unit": dimensions["unit"],
            "country_count": dimensions["country_count"], "industry_count": dimensions["industry_count"],
            "matrix_sha256": descriptor["sha256"], "readme_sha256": README_SHA256,
            "matrix_archive_member": descriptor["member"], "source_url": PUBLISHER_PAGE,
            "publisher_direct_verified": True, "common_update_verified": True,
            "replica_content_hash_verified": False,
            "independent_replica_match_verified": replica == descriptor["sha256"],
            "full_history_verified": False, "first_publication_verified": False,
            "rights": "OECD ICIO CC BY 4.0",
            "limitations": ["Publisher archive downloaded by the owner in a browser; the automated route is a Cloudflare challenge.",
                "Archive and member bytes are pinned on receipt; 2016-2022 also match independent public replicas.",
                "Accounting residuals above serialization rounding are retained without rebalancing.",
                "The regular table cannot reproduce extended-table TiVA exactly; no Leontief or shock result is certified."]}


def store_icio_publisher_archive(archive: Path, readme: Path, evidence_root: Path) -> list[Path]:
    """Retain one owner-downloaded OECD archive and each of its year matrices."""
    archive, readme = Path(archive), Path(readme)
    expected = PUBLISHER_ARCHIVES.get(archive.name)
    if (expected is None or archive.is_symlink() or readme.is_symlink()
            or archive.stat().st_size != expected["bytes"] or _hash(archive) != expected["sha256"]
            or _hash(readme) != README_SHA256):
        raise ValueError("icio_pinned_original_identity_mismatch")
    years = sorted(year for year, item in PUBLISHER_MATRICES.items() if item["archive"] == archive.name)
    listing = {"archive": archive.name, "archive_sha256": expected["sha256"],
               "members": {PUBLISHER_MATRICES[y]["member"]: PUBLISHER_MATRICES[y]["sha256"] for y in years},
               "matrix_sha256": expected["sha256"]}
    identity = {"publisher": "OECD", "edition": "2025", "update": "January 2026", "table": "regular",
                "acquisition": "owner_browser_download", "archive": archive.name}
    root = Path(evidence_root) / "icio"
    stored = [_store_original_bundle(root / f"regular-2025-archive-{archive.stem}", {"archive.zip": archive},
              listing, identity, {"archive": f"{PUBLISHER_PAGE}#{archive.name}"},
              lambda bundle: _verified_manifest(bundle, identity, {"archive.zip", "audit.json"},
                                                {"archive": f"{PUBLISHER_PAGE}#{archive.name}"}, expected["sha256"]))]
    with zipfile.ZipFile(archive) as package, tempfile.TemporaryDirectory(dir=root) as scratch:
        for year in years:
            descriptor = PUBLISHER_MATRICES[year]
            info = package.getinfo(descriptor["member"])
            if info.file_size != descriptor["bytes"]:
                raise ValueError("icio_archive_member_invalid")
            matrix = Path(scratch) / descriptor["member"]
            with package.open(info) as source, matrix.open("wb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            if _hash(matrix) != descriptor["sha256"]:
                raise ValueError("icio_original_matrix_hash_mismatch")
            audit = _publisher_audit(str(matrix), str(readme), year)
            stored.append(_store_original_bundle(root / f"regular-2025-{year}-publisher",
                {"matrix.csv": matrix, "readme.xlsx": readme}, audit, _publisher_identity(year),
                _publisher_sources(year), lambda bundle, y=year: _verify_publisher_bundle(bundle, y)))
            matrix.unlink()
    return stored


def _verify_publisher_bundle(bundle, year):
    descriptor = PUBLISHER_MATRICES[year]
    manifest = _verified_manifest(bundle, _publisher_identity(year), {"matrix.csv", "readme.xlsx", "audit.json"},
                                  _publisher_sources(year), descriptor["sha256"])
    if manifest["files"]["matrix.csv"] != descriptor["sha256"] or manifest["files"]["readme.xlsx"] != README_SHA256:
        raise ValueError("icio_pinned_original_identity_mismatch")
    audit = json.loads((bundle / "audit.json").read_bytes())
    _verify_audit_pin(audit, descriptor["sha256"], year, PUBLISHER_AUDIT_METHOD)
    return audit


def read_icio_evidence(evidence_root: Path, *, include_residuals: bool = False) -> dict:
    from .source_reconciliation import _selected_manifest
    publisher = {}
    for year in sorted(PUBLISHER_MATRICES):
        parent_dir = Path(evidence_root) / "icio" / f"regular-2025-{year}-publisher"
        if parent_dir.exists():
            observed, manifest_hash, path, _manifest, selection = _selected_manifest(parent_dir, _publisher_identity(year))
            audit = _verify_publisher_bundle(path.parent, year)
            publisher[year] = {**audit, "materiality": material_accounting(audit),
                "original_source_hash_verified": True, "bundle_digest": path.parent.name,
                "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
                "selection_method": selection}
    historical = []
    for year in sorted(HISTORY_MATRICES):
        if year in publisher:
            continue
        history_parent = Path(evidence_root) / "icio" / f"regular-2025-{year}-replica"
        if history_parent.exists():
            observed, manifest_hash, path, _manifest, selection = _selected_manifest(history_parent, _history_identity(year))
            replica = _verify_historical_bundle(path.parent, year)
            historical.append({**replica, "materiality": material_accounting(replica),
                "original_source_hash_verified": True, "bundle_digest": path.parent.name,
                "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
                "selection_method": selection})
    historical = sorted(historical + list(publisher.values()), key=lambda item: item["year"])
    parent = Path(evidence_root) / "icio" / "regular-2025-2022"
    if 2022 in publisher:
        primary = dict(publisher[2022])
    elif parent.exists():
        observed, manifest_hash, path, _manifest, selection = _selected_manifest(parent, IDENTITY)
        audit = _verify_icio_bundle(path.parent)
        if include_residuals:
            audit = diagnose_icio_package(path.parent / "package.zip", path.parent / "readme.xlsx")
        primary = {**audit, "original_source_hash_verified": True, "bundle_digest": path.parent.name,
            "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
            "selection_method": selection}
    elif historical:
        primary = dict(historical[-1])
    else:
        primary = {"full_history_verified": False, "first_publication_verified": False,
                   "original_source_hash_verified": False}
    if "materiality" not in primary and primary.get("original_source_hash_verified"):
        primary["materiality"] = material_accounting(primary)
    verified_years = sorted({item["year"] for item in historical} | ({2022} if parent.exists() else set()))
    full = verified_years == list(range(1995, 2023))
    # One edition and update for every year only when each year is the
    # publisher's own January 2026 archive member.
    common = full and set(publisher) == set(range(1995, 2023))
    coverage = {"required_years": [1995, 2022], "verified_years": verified_years,
                "missing_years": sorted(set(range(1995, 2023)) - set(verified_years)),
                "publisher_direct_years": sorted(publisher),
                "replica_only_years": sorted(item["year"] for item in historical
                                             if not item.get("publisher_direct_verified")
                                             and not item["independent_replica_match_verified"]),
                "full_history_verified": full,
                "first_publication_verified": False, "common_update_verified": common,
                "material_accounting_passed_years": sorted(item["year"] for item in historical
                    if item["materiality"]["material_accounting_passed"])}
    material = full and all(item["materiality"]["material_accounting_passed"] for item in historical)
    status = ("verified_full_history_original_matrices" if common and material else
              (f"verified_{primary['year']}_original_matrix" if primary.get("accounting_passed")
               else "original_matrix_accounting_failed")) if verified_years else "missing_original_matrix"
    from .icio_release_diagnostics import read_2022_release_comparison
    comparison = read_2022_release_comparison(evidence_root, verified_newer_sha256=(
        primary.get("matrix_sha256") if primary.get("original_source_hash_verified") else None))
    from .oecd_icio_access import read_publisher_access
    return {**primary, "status": status, "historical_matrices": historical, "historical_coverage": coverage,
            "release_comparison": comparison, "publisher_acquisition": read_publisher_access(evidence_root)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    original = parser.add_mutually_exclusive_group(required=True)
    original.add_argument("--package", type=Path)
    original.add_argument("--matrix", type=Path, help="A registered, pinned original replica CSV")
    original.add_argument("--publisher-archive", type=Path, action="append",
                          help="A pinned OECD 2025 regular archive downloaded by the owner (repeatable)")
    parser.add_argument("--year", type=int, choices=sorted(HISTORY_MATRICES))
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--diagnose", action="store_true", help="Read-only signed residual investigation; do not store or rewrite source evidence")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    args = parser.parse_args()
    if args.publisher_archive:
        for archive in args.publisher_archive:
            for bundle in store_icio_publisher_archive(archive, args.readme, args.root):
                print(bundle.parent.name, bundle.name, flush=True)
        coverage = read_icio_evidence(args.root)["historical_coverage"]
        print(json.dumps(coverage, indent=2))
        return
    if args.matrix:
        if args.year is None:
            parser.error("--matrix requires --year")
        if args.diagnose:
            _verify_matrix_pins(args.matrix, args.readme, args.year)
            print(json.dumps(_historical_audit(str(args.matrix.resolve()), str(args.readme.resolve()),
                args.year, HISTORY_MATRICES[args.year]["sha256"]), indent=2))
        else:
            bundle = store_icio_matrix(args.matrix, args.readme, args.year, args.root)
            print(json.dumps(_verify_historical_bundle(bundle, args.year), indent=2))
        return
    if args.year is not None:
        parser.error("--year applies to --matrix")
    if args.diagnose:
        print(json.dumps(diagnose_icio_package(args.package, args.readme), indent=2))
        return
    store_icio_package(args.package, args.readme, args.root)
    print(json.dumps(read_icio_evidence(args.root), indent=2))


if __name__ == "__main__": main()
