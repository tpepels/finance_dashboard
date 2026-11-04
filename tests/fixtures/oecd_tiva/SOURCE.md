# OECD TiVA original response fixtures

Publisher: OECD. Edition: 2025, January 2026 revision; SDMX dataflow version 1.1.
Country totals: USA/FRA/PRT/CHN/JPN/DEU/IND, activity `_T`, counterpart `W`, annual 1995–2022.
Original responses acquired 2026-11-04; exact original bytes, no reserialization.

- `tiva_2025_levels.csv`: 392 observations, current USD millions, SHA-256 `fe2e53c3c7b3487cab360cb85898f8fe04de288d2a1cd7e1989b4d4a1364fdc7`.
- `tiva_2025_shares.csv`: 196 observations, percent of VALU, SHA-256 `5050b1aad7f89e041ad900ceb73ae9b40d3abe5ff277a11e3c35b884ae9d6008`.

Original selected-country URLs (query `startPeriod=1995&dimensionAtObservation=AllDimensions`, Accept `text/csv`):

- [Levels](https://sdmx.oecd.org/sti-public/rest/data/OECD.STI.PIE,DSD_TIVA_MAINLV@DF_MAINLV,1.1/FFD_DVA+VALU.USA+FRA+PRT+CHN+JPN+DEU+IND._T.W.USD.A)
- [Shares](https://sdmx.oecd.org/sti-public/rest/data/OECD.STI.PIE,DSD_TIVA_MAINSH@DF_MAINSH,1.1/FFD_DVA.USA+FRA+PRT+CHN+JPN+DEU+IND._T.W.PT_VA.A)
- [OECD 2025 Guide](https://stats.oecd.org/wbos/fileview2.aspx?IDFile=2143f34e-6feb-41a9-abaf-cb52132608c4), September 2025, printed pages 13 and 34; retrieved PDF SHA-256 `ca3f3db9024a6f870ff6bec061537ea2230abf7880a8e56c3f5c16cd5518bdb4`.

[OECD terms](https://www.oecd.org/en/about/terms-conditions.html), CC BY 4.0 attribution. Original acquisition manifest/receipts and full publisher documentation are preserved separately under private source evidence. Retrieval is not original first publication, and the two response bodies do not prove a synchronized release.

The fixture intentionally retains the original discrepancies. The existing 0.001pp test fails for nine country-years (three distinct years). Interval accounting of the independently printed three-decimal levels and shares finds 46 country-years inconsistent with serialization rounding alone. This sharper diagnostic neither changes the existing tolerance nor establishes the cause.
