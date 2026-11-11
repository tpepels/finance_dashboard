import type { Bundle } from './analysisShell';
import { historyPosition } from './analysisShell';
import { ENTITY, entityName, type Theme } from './chartKit';
import { EpisodeBars, PhaseBoard, RateLadder, RankedBars, ReturnRuler, StackedShares, Thermometers,
  type ClockRow, type Episode, type RulerMarker } from './heroes';
import type { C01Values } from './GrowthPanel';
import type { M01Values } from './MonetaryPanel';
import type { F03Values, P06Values, P06Estimates } from './DecisionPanel';

type Gauge = { key: string; name: string; unit: string; latest: number; as_of: string; own_mean: number; own_percentile: number | null; min: number; max: number };
type Split = { economies: { area: string; year: string; parts: { key: string; share: number }[] }[] };
const SPLIT_LABELS = { compensation: 'Wages and salaries', net_operating_surplus: 'Net operating surplus', depreciation: 'Depreciation',
  net_production_taxes: 'Production taxes (net)', remainder: 'Unallocated remainder' };

/** Only the lead graphic: no histories, editors, configured figures or additional reads. */
export default function DashboardLead({ id, bundle, theme }: { id: string; bundle: Bundle<unknown, unknown>; theme: Theme }) {
  switch (id) {
    case 'P06': {
      const data = bundle.values as P06Values;
      const equity = (bundle.estimates as P06Estimates | null)?.equity_us;
      const markers: RulerMarker[] = [];
      if (data.bonds.us_real_10y) markers.push({ label: 'US inflation-linked 10y', value: data.bonds.us_real_10y.yield, slot: 2,
        note: `yield on ${data.bonds.us_real_10y.as_of}` });
      if (data.bonds.ea_aaa_10y_real_trailing) markers.push({ label: 'Euro AAA 10y after inflation', value: data.bonds.ea_aaa_10y_real_trailing.yield,
        slot: 3, note: 'nominal yield minus trailing HICP inflation' });
      if (data.equity_world_snapshot) markers.push({ label: 'World equities earnings yield', value: data.equity_world_snapshot.earnings_yield,
        slot: 4, note: `snapshot ${data.equity_world_snapshot.as_of}` });
      if (data.ea_inflation) markers.push({ label: 'Euro-area inflation, 12m', value: data.ea_inflation.rate, kind: 'inflation', note: `to ${data.ea_inflation.month}` });
      return <ReturnRuler theme={theme} markers={markers} equity={equity?.range_real
        ? { ...equity.range_real, label: 'US equities after inflation, next 10 years' } : null}/>;
    }
    case 'C01': return <PhaseBoard theme={theme} rows={(bundle.values as C01Values).clock as ClockRow[]}/>;
    case 'M01': {
      const data = bundle.values as M01Values;
      return <RateLadder theme={theme} banks={data.ladder} target={data.fed_target} gaps={[
        { label: 'Euro minus dollar', value: data.gaps.eur_minus_usd.at(-1)?.[1] ?? null },
        { label: 'Euro minus yen', value: data.gaps.eur_minus_jpy.at(-1)?.[1] ?? null }]}/>;
    }
    case 'F03': {
      const data = bundle.values as F03Values;
      const rows = data.rows.filter(row => row.area in ENTITY && row.credit_gap && data.history[row.area]?.credit_gap_range)
        .map(row => ({ area: row.area, latest: row.credit_gap!.latest, mean: row.credit_gap!.own_mean,
          asOf: row.credit_gap!.as_of, ...data.history[row.area].credit_gap_range! }));
      return <Thermometers theme={theme} title="Credit gap" unit="pp" rows={rows}
        zones={[{ from: data.guide.low_pp, to: data.guide.high_pp }, { from: data.guide.high_pp, to: null }]}/>;
    }
    case 'V01': return <Thermometers theme={theme} title="US equity valuation" unit="" rows={(bundle.values as { gauges: Gauge[] }).gauges.map(gauge => ({
      area: gauge.key, label: gauge.name, min: gauge.min, max: gauge.max, mean: gauge.own_mean, latest: gauge.latest,
      asOf: gauge.as_of, note: historyPosition(gauge.own_percentile), format: value => gauge.unit === '%' ? `${value.toFixed(1)}%`
        : gauge.unit === 'pp' ? `${value.toFixed(2)} pp` : `${value.toFixed(1)}×` }))}/>;
    case 'P03': return <EpisodeBars theme={theme} episodes={(bundle.values as { episodes: Episode[] }).episodes}/>;
    case 'G01': {
      const data = bundle.values as { latest: { date: string; issuers: { name: string; pct: number }[] } | null };
      return <RankedBars theme={theme} title={`Largest ETF issuer-name groups · ${data.latest?.date ?? 'no filing'}`} rows={data.latest?.issuers.slice(0, 10) ?? []}/>;
    }
    case 'L02': return <StackedShares theme={theme} title="How company value added is split" labels={SPLIT_LABELS}
      rows={(bundle.values as Split).economies.map(row => ({ key: row.area, label: `${entityName(row.area)} ${row.year}`, parts: row.parts }))}/>;
    default: return null;
  }
}
