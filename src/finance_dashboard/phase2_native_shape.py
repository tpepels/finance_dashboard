"""Typed invariants shared by all 28 explicitly registered native inputs.

Native syntactic constraints can be verified generically. They cannot certify
the methodological meaning of a publisher's account, FX rate, issuer mapping,
portfolio weight, published event or policy without source-specific evidence.
These requirements are deliberately uniform across analyses and publishers.
"""
from __future__ import annotations


REQUIRED_ORIGINAL_SHAPES = {
    "events": {"date": True, "numeric": False, "related_entity": False},
    "fx_history": {"date": True, "numeric": True, "related_entity": False},
    "accounting_panel": {"date": True, "numeric": True, "related_entity": False},
    "positions": {"date": True, "numeric": True, "related_entity": True},
    "allocation": {"date": True, "numeric": True, "related_entity": True},
    "policy": {"date": True, "numeric": False, "related_entity": False},
    "scenario_parameter": {"date": True, "numeric": True, "related_entity": False},
    "entity_mapping": {"date": False, "numeric": False, "related_entity": True},
    "filing_panel": {"date": True, "numeric": True, "related_entity": True},
    "matrix": {"date": True, "numeric": True, "related_entity": True},
}


def typed_original_checks(role: dict, schema: dict, facts: dict) -> dict:
    kind = role["input_type"]
    shape = REQUIRED_ORIGINAL_SHAPES.get(kind)
    if shape is None:
        raise ValueError("unsupported_structured_original_input_type")
    fields = schema["fields"]
    keys = schema["key_fields"]
    numbers = schema["numeric_fields"]
    date_field = schema["date_field"]
    if shape["date"] and date_field is None:
        raise ValueError("original_temporal_input_requires_native_date_column")
    if shape["numeric"] and not numbers:
        raise ValueError("original_numeric_input_requires_numeric_column")
    if shape["numeric"] and facts["numeric_values_reported"] == 0:
        raise ValueError("original_numeric_input_contains_no_numeric_values")
    if shape["related_entity"] and len(fields) <= len(keys):
        raise ValueError("original_relational_input_requires_related_field")
    if not facts["record_count"] or facts["record_count"] != facts[
            "distinct_original_record_keys"]:
        raise ValueError("original_record_keys_not_unique")
    return {
        "original_input_type": kind,
        "original_record_keys_unique": True,
        "native_timeline_column_reported": date_field is not None,
        "native_numeric_fields_reported": bool(numbers),
        "native_relational_fields_reported": len(fields) > len(keys),
        "source_rows_syntactically_valid": True,
        "all_numerical_observations_reconciled_to_publisher": False,
        "source_native_currency_and_scale_verified": False,
        "original_population_perimeter_verified": False,
        "unmodified_original_publication_available_on_event_date": False,
        "first_publication_verified": False,
        "original_method_acceptance": False,
    }
