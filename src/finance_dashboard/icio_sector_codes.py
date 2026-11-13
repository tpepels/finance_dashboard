"""Explicit publisher CSV activity codes for each OECD ICIO edition.

The existing D-prefixed economic codes are internal analytical identifiers.
Publisher native CSVs use bare numeric codes (2018/2021) or lettered
ISIC activity identifiers (2023/2025). This is a one-to-one semantic label
translation only; it never aggregates or apportions matrix values.

Source: OECD ICIO edition annexes/ReadMe; exvatools extract_icio sector lists.
"""
from __future__ import annotations

from .icio_native import SECTORS_2018, SECTORS_2021, SECTORS_2025

SOURCE_SECTORS_2018 = [code.removeprefix("D") for code in SECTORS_2018]
SOURCE_SECTORS_2021 = [code.removeprefix("D") for code in SECTORS_2021]
SOURCE_SECTORS_2023 = """
A01_02 A03 B05_06 B07_08 B09 C10T12 C13T15 C16 C17_18 C19
C20 C21 C22 C23 C24 C25 C26 C27 C28 C29 C30 C31T33 D E F G
H49 H50 H51 H52 H53 I J58T60 J61 J62_63 K L M N O P Q R S T
""".split()
SOURCE_SECTORS_2025 = """
A01 A02 A03 B05 B06 B07 B08 B09 C10T12 C13T15 C16 C17_18
C19 C20 C21 C22 C23 C24A C24B C25 C26 C27 C28 C29 C301 C302T309
C31T33 D E F G H49 H50 H51 H52 H53 I J58T60 J61 J62_63 K L
M N O P Q R S T
""".split()

SOURCE_BY_EDITION = {"2018": SOURCE_SECTORS_2018,
                     "2021": SOURCE_SECTORS_2021,
                     "2023": SOURCE_SECTORS_2023,
                     "2025": SOURCE_SECTORS_2025}
INTERNAL_BY_EDITION = {"2018": SECTORS_2018, "2021": SECTORS_2021,
                       "2023": SECTORS_2021, "2025": SECTORS_2025}

for release in SOURCE_BY_EDITION:
    source = SOURCE_BY_EDITION[release]
    internal = INTERNAL_BY_EDITION[release]
    if (len(source) != len(internal) or len(set(source)) != len(source)
            or len(set(internal)) != len(internal)):
        raise AssertionError("icio_native_sector_concordance_invalid_" + release)


def source_sector_map(edition: str) -> dict[str, str]:
    return dict(zip(SOURCE_BY_EDITION[edition], INTERNAL_BY_EDITION[edition]))


def normalize_native_sector_labels(codes: list[str], edition: str) -> dict[str, str]:
    """Require the COMPLETE vocabulary from exactly one source layout.

    Existing D-coded fixtures remain supported for the same edition, but a
    mixture or unidentified vocabulary never enters economic reconstruction.
    """
    source = source_sector_map(edition)
    observed = set(codes)
    if len(observed) != len(codes):
        raise ValueError("icio_native_duplicate_industry_code")
    if observed == set(source):
        return source
    canonical = INTERNAL_BY_EDITION[edition]
    if observed == set(canonical):
        return {code: code for code in canonical}
    raise ValueError("icio_native_industry_dimensions_mismatch")
