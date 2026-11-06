"""Canonical registration of all supported data-source adapters.

Selection, refresh scope and evidence collection behavior are described once
per source family. A new provider must register a callable and its guarantees.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderRegistration:
    code: str
    handler: str
    acquisition: str  # response, native, local, derived, unsupported
    refresh_scope: str  # full or windowed
    complete_source_keys: frozenset[str] = frozenset()

    def requires_full_refresh(self, key: str) -> bool:
        return self.refresh_scope == "full" or key in self.complete_source_keys

_REGISTRATIONS = (
    ProviderRegistration("BIS", "fetch_bis", "response", "windowed"),
    ProviderRegistration("WID", "fetch_wid", "native", "full"),
    ProviderRegistration("OECD_TIVA", "fetch_oecd_tiva", "native", "full"),
    ProviderRegistration("FRENCH_RETURNS", "fetch_french_returns", "native", "full"),
    ProviderRegistration("SWINKELS_RETURNS", "fetch_french_returns", "native", "full"),
    ProviderRegistration("GLOBAL_MARKET_RETURNS", "fetch_french_returns", "native", "full"),
    ProviderRegistration("FRED", "fetch_fred", "response", "windowed", frozenset({"NFCI", "ANFCI"})),
    ProviderRegistration("ECB", "fetch_ecb", "response", "windowed"),
    ProviderRegistration("WORLD_BANK", "fetch_world_bank", "response", "windowed"),
    ProviderRegistration("WORLD_LISTED_CAP_SHARE", "fetch_world_listed_cap_share", "response", "windowed"),
    ProviderRegistration("SIBLIS_WORLD_PE", "fetch_siblis_world_pe", "response", "full"),
    ProviderRegistration("SIBLIS_WORLD_EARNINGS_YIELD", "fetch_siblis_world_pe", "response", "full"),
    ProviderRegistration("MSCI_PUBLISHED_TOP10", "fetch_msci_published_top10", "native", "windowed"),
    ProviderRegistration("OECD_CORPORATE_GDPWEIGHTED", "fetch_oecd_corporate_gdpweighted", "response", "windowed"),
    ProviderRegistration("EUROSTAT_CORPORATE_GDP", "fetch_eurostat_corporate_gdp", "response", "windowed"),
    ProviderRegistration("EUROSTAT_NFC_PROFIT_GVA", "fetch_eurostat_nfc_profit_gva", "response", "windowed"),
    ProviderRegistration("BIS_WORLD_WEIGHTED", "fetch_bis_world_weighted", "response", "windowed"),
    ProviderRegistration("ILO_LABOUR_PRODUCTIVITY_RATIO", "fetch_ilo_labour_productivity_ratio", "derived", "windowed"),
    ProviderRegistration("WISESHEETS_SNAPSHOT", "fetch_wisesheets_snapshot", "local", "windowed"),
    ProviderRegistration("BEA_Q", "fetch_bea_q", "response", "full"),
    ProviderRegistration("MSCI_NETR", "fetch_msci_netr", "response", "windowed"),
    ProviderRegistration("GOLD_MSCI_CORR", "fetch_gold_msci_corr", "response", "full"),
    ProviderRegistration("CORGANO_SPOT", "fetch_corgano_spot", "response", "windowed"),
    ProviderRegistration("BIS_PROPERTY", "fetch_bis_property", "response", "windowed"),
    ProviderRegistration("BIS_DSR", "fetch_bis_dsr", "response", "windowed"),
    ProviderRegistration("BIS_CREDIT_GAP", "fetch_bis_credit_gap", "response", "windowed"),
    ProviderRegistration("BIS_TOTAL_CREDIT", "fetch_bis_total_credit", "response", "full"),
    ProviderRegistration("FED_G17_DIFFUSION", "fetch_fed_g17_diffusion", "response", "full"),
    ProviderRegistration("OFR_FSI", "fetch_ofr_fsi", "response", "full"),
    ProviderRegistration("BOJ_TSS", "fetch_boj_tss", "response", "full"),
    ProviderRegistration("OECD_CLI", "fetch_oecd_cli", "response", "full"),
    ProviderRegistration("IMF_BOP_IIP", "fetch_imf_bop_iip", "response", "full"),
    ProviderRegistration("FDIC_BANKFIND", "fetch_fdic_bankfind", "response", "full"),
    ProviderRegistration("SIBLIS_FREE", "fetch_siblis_free", "response", "windowed"),
    ProviderRegistration("WORLD_BANK_PINK_SHEET", "fetch_world_bank_pink_sheet", "response", "full"),
    ProviderRegistration("UN_SDG", "fetch_un_sdg", "response", "windowed"),
    ProviderRegistration("SHILLER", "fetch_shiller", "response", "full"),
    ProviderRegistration("IMF_DATAMAPPER", "fetch_imf_datamapper", "response", "full"),
)
PROVIDER_REGISTRY = {entry.code: entry for entry in _REGISTRATIONS}
PROVIDER_CODES = frozenset(PROVIDER_REGISTRY)
if len(PROVIDER_REGISTRY) != len(_REGISTRATIONS):
    raise RuntimeError("Duplicate provider registration")

def get_provider(code: str) -> ProviderRegistration | None:
    return PROVIDER_REGISTRY.get(code)
