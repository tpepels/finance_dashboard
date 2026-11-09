# Phase 3 visual language: a dashboard for people

Status: owner-approved direction, 2026-11-09. Extends the [engine design](2026-11-08-phase3-engine-design.md). Applies to the Decisions panel first and to every later overview group.

## Owner brief

Visual representation, not tables. Numbers without a time axis get a graphic tied to their meaning (a ruler, a map, a thermometer), not a table. Charts must be analysable: a wide, distinguishable colour range, zoom, and visible recession periods (dot-com, 2008, COVID). A dashboard for humans; the AI export stays available but secondary.

## Shared chart language

* **Recessions.** All NBER US recessions from the stored monthly indicator (`recession.us.nber_indicator`, 1854–) shade every time chart. Dot-com 2001, the financial crisis 2008–09 and COVID-19 2020 carry their names on the chart; every band names itself on hover. On non-US charts the bands are labelled "US recession".
* **Zoom and analysis.** Wheel/pinch zoom, a range slider, presets (5Y, 10Y, 20Y, All), a crosshair tooltip with every series at that date and the recession it falls in, legend toggles, linked zoom and crosshair across small multiples.
* **Colour.** The validated eight-hue categorical palette (dataviz reference instance), stepped separately for light and dark; colour follows the entity everywhere. Status red/green are never series colours. Diverging values (above/below zero) use blue↔red with a grey midpoint.
* **Type.** Atkinson Hyperlegible Next, bundled locally.
* **Section layout.** Question → hero graphic ("where are we now") → history charts → folded limitations and "Export for AI".
* **No tables in the default view.** An accessible data view is reachable but closed.

## Decisions

* **P06** — return ruler (one real-return scale: equity p10–p90 band with median, bond real yields and inflation as markers); CAPE history since 1881 with today marked; calibration cloud (starting earnings yield vs realised next-10-year real return, today's yield marked).
* **P07** — risk–return map (unhedged and hedged, arrow between); wealth of 100 EUR (log); underwater drawdown; hedge carry over time (diverging around zero).
* **F03** — own-history thermometers per economy (credit gap with BIS 2/10 pp zones; debt service with its own mean); small multiples per economy with BIS zones and own-mean lines.

## Engine additions

Bundles carry the histories each graphic draws (P06 CAPE history and calibration points; P07 drawdowns; F03 per-economy histories and own-history ranges), recorded as named transforms; `/api/recessions` serves the NBER periods. Existing numbers do not change.
