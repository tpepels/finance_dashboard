import type { ChartDefinition } from './types';

// A fixed, economic-question-led reading order. There are no automatically
// generated pairings based only on an axis unit or source country.
export interface Chapter {
  id: string;
  name: string;
  question: string;
  chartIds: string[];
}
export const CHAPTERS: Chapter[] = [
  { id: 'monetary_policy', name: '01 / Monetary policy',
    question: 'Are major central banks moving together or apart?',
    chartIds: ['policy_rates_global'] },
  { id: 'growth_inflation', name: '02 / Economic growth',
    question: 'Which major economies are accelerating or slowing?',
    chartIds: ['gdp_growth_global'] },
  { id: 'credit_recession', name: '03 / Credit cycle',
    question: 'How far is private credit from its long-run trend?',
    chartIds: ['bis_credit_gaps', 'world_bis_credit_cycle_composite', 'world_bis_credit_cycle_gdp_coverage'] },
  { id: 'valuation', name: '04 / Equity valuations',
    question: 'How large and highly valued are listed equity markets?',
    chartIds: ['domestic_equity_value', 'world_listed_cap_share', 'world_listed_cap_usd',
      'world_aggregate_trailing_pe', 'world_aggregate_earnings_yield'] },
  { id: 'labour_capital', name: '05 / Labour and corporate income',
    question: 'How are output and gross operating surplus distributed?',
    chartIds: ['world_labour_income_share', 'world_productivity_growth',
      'oecd38_corporate_surplus_gdp', 'eu27_corporate_gos_gdp',
      'eu27_nfc_operating_surplus_gva', 'oecd38_corporate_surplus_coverage',
      'oecd38_corporate_surplus_members'] },
  { id: 'market_concentration', name: '06 / Equity concentration',
    question: 'How much of a global equity index is concentrated in its top holdings?',
    chartIds: ['global_msci_acwi_top10_snapshots'] },
  { id: 'gold_currency', name: '07 / Gold and equities',
    question: 'Does gold move with or independently of global equities?',
    chartIds: ['gold_vs_global_index_netr', 'monthly_gold_prices'] },
  { id: 'structural_risk', name: '08 / Public debt',
    question: 'What does the measured history say about world public debt?',
    chartIds: ['world_public_debt'] },
];

export interface Commentary { question: string; reading: string; limitation: string }
export const EDITORIAL: Record<string, Commentary> = {
  policy_rates_global: {
    question: 'Policy divergence',
    reading: 'Compare the common-date level and spread of BIS harmonized policy rates. Divergence signals different monetary stances, not a prediction of currencies or asset prices.',
    limitation: 'BIS harmonized series may splice policy instruments through history.',
  },
  gdp_growth_global: {
    question: 'Relative growth cycles',
    reading: 'Compare annual real GDP growth rates across the same reference years. A world aggregate overlaps its country components; readings are not additive.',
    limitation: 'Country growth rates and world aggregate have different weights and can be revised.',
  },
  bis_credit_gaps: {
    question: 'Credit-cycle pressure',
    reading: 'A positive BIS credit gap indicates credit-to-GDP above its country-specific statistical trend; a negative gap indicates below-trend credit.',
    limitation: 'This is a trend gap in percentage points, not the credit growth rate or crisis probability.',
  },
  world_bis_credit_cycle_composite: {
    question: 'Cross-country credit imbalance',
    reading: 'The GDP-weighted composite tracks reporting economies relative to their BIS credit-to-GDP trends. Read alongside its separate GDP coverage chart.',
    limitation: 'Researcher-computed weighted composite, not an official BIS world figure.',
  },
  world_bis_credit_cycle_gdp_coverage: {
    question: 'Can the world credit series be interpreted?',
    reading: 'Shows the share of world GDP represented in the accompanying credit-gap composite. Changes in reporting coverage can affect historical interpretation.',
    limitation: 'Coverage is not a measure of credit risk.',
  },
  domestic_equity_value: {
    question: 'Domestic equity-market depth',
    reading: 'Compare country-specific listed market capitalization relative to each economy’s GDP; higher ratios need not imply greater overvaluation.',
    limitation: 'Listings, corporate residence and market coverage differ; neither figure is global market capitalization.',
  },
  world_listed_cap_share: {
    question: 'Global listed capitalization relative to output',
    reading: 'Follow the share of world nominal GDP represented by domestic listed-company capitalization. A changing ratio may reflect prices, listings and GDP together.',
    limitation: 'This is the World Bank world aggregate, not a full valuation multiple.',
  },
  world_listed_cap_usd: {
    question: 'Scale of listed markets',
    reading: 'Tracks world nominal listed-capitalization levels, not real wealth or inflation-adjusted purchasing power.',
    limitation: 'Measured in current USD: exchange rates, prices and listing changes all affect the series.',
  },
  world_aggregate_trailing_pe: {
    question: 'What multiple of earnings is paid?',
    reading: 'Higher trailing P/E typically implies higher prices relative to the same index universe’s reported trailing earnings.',
    limitation: 'Siblis observations are sparse published snapshots, not a continuous monthly history or an all-listed worldwide universe.',
  },
  world_aggregate_earnings_yield: {
    question: 'Earnings relative to index price',
    reading: 'The reciprocal of the same global index’s trailing P/E. Falling yield can reflect increasing prices, lower earnings or both.',
    limitation: 'Do not combine its index earnings yield with unmatched World Bank all-market capitalization.',
  },
  world_labour_income_share: {
    question: 'Share of output received by labour',
    reading: 'The income-share level measures labour’s portion of output, including the underlying source’s treatment of self-employment.',
    limitation: 'This is a share of income, not a wage growth rate.',
  },
  world_productivity_growth: {
    question: 'World labour productivity',
    reading: 'Tracks year-on-year change in worldwide real output per worker/hour as specified by the source.',
    limitation: 'A growth rate cannot be compared directly on one axis with the labour income-share level.',
  },
  oecd38_corporate_surplus_gdp: {
    question: 'OECD corporate operating surplus',
    reading: 'Shows GDP-weighted financial and nonfinancial gross operating surplus relative to GDP across sufficiently covered current OECD members.',
    limitation: 'Both listed and unlisted corporations; not worldwide listed-company net profits. See member and GDP coverage charts.',
  },
  eu27_corporate_gos_gdp: {
    question: 'EU corporate operating surplus',
    reading: 'The financial and nonfinancial corporate sectors’ gross operating surplus as a percentage of EU GDP.',
    limitation: 'EU27 current boundaries. Not the same reporting universe as OECD or listed-company net income.',
  },
  eu27_nfc_operating_surplus_gva: {
    question: 'Nonfinancial corporate surplus ratio',
    reading: 'The EU nonfinancial corporate operating-surplus share is measured against sector gross value added.',
    limitation: 'Denominator is nonfinancial value added, not whole-economy GDP; do not overlay the EU corporate surplus/GDP series.',
  },
  oecd38_corporate_surplus_coverage: {
    question: 'Is OECD participation broad enough?',
    reading: 'Shows the share of current OECD member GDP included in the operating-surplus calculation.',
    limitation: 'A coverage statistic, not a profit share.',
  },
  oecd38_corporate_surplus_members: {
    question: 'How many OECD members report?',
    reading: 'Counts member-country-years contributing validated surplus and GDP observations.',
    limitation: 'The 38-member label denotes the eligible membership universe, not 38 observed members in every year.',
  },
  global_msci_acwi_top10_snapshots: {
    question: 'Concentration in the largest stocks',
    reading: 'An increasing top-ten weight means a larger fraction of the MSCI ACWI index is held in its largest constituents at the recorded snapshot date.',
    limitation: 'Sparse actual MSCI snapshots; no invented monthly constituent weights.',
  },
  gold_vs_global_index_netr: {
    question: 'Gold versus global equities',
    reading: 'Rolling 36-month correlation of matched monthly gold and MSCI ACWI net-total-return observations. Positive values mean historically co-moving returns; negative values imply opposite directions.',
    limitation: 'Historical correlation is not causal evidence or a forward forecast; the window changes over time.',
  },
  monthly_gold_prices: {
    question: 'Gold quoted in dollars',
    reading: 'World Bank gold monthly average in nominal USD per troy ounce.',
    limitation: 'Monthly averages are not daily spot prices or inflation-adjusted returns.',
  },
  world_public_debt: {
    question: 'Worldwide sovereign debt',
    reading: 'Follow the official estimate of worldwide public-debt burden as the source defines it.',
    limitation: 'Fiscal debt and a daily US policy rate measure different economic quantities and should not be overlaid.',
  },
};

// Only genuinely equivalent measurement families may be overlaid.
// A matching display unit, country, or visual normalization is insufficient.
export function measureFamily(seriesId: string): string {
  if (/^policy_rate\.(us|ea|jp)\.bis$/.test(seriesId)) return 'bis_harmonized_policy';
  if (/^gdp\.real_growth\./.test(seriesId)) return 'real_gdp_growth';
  if (/^credit_gap\.(us|ea|jp)\.bis$/.test(seriesId)) return 'bis_credit_gap';
  if (/^valuation\.domestic_cap_gdp\.(us|jp)$/.test(seriesId)) return 'domestic_equity_cap_to_gdp';
  return seriesId;
}

export function semanticallyCompatible(ids: string[]): boolean {
  return ids.length === 0 || ids.every(id => measureFamily(id) === measureFamily(ids[0]));
}

export function curatedCharts(charts: ChartDefinition[], ids: string[]): ChartDefinition[] {
  return ids.flatMap(id => charts.filter(c => c.id === id &&
    c.status === 'mapped' && semanticallyCompatible(c.series_ids)));
}
