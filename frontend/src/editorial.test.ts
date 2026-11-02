import { describe, expect, it } from 'vitest';
import { curatedCharts, measureFamily, semanticallyCompatible } from './editorial';
import type { ChartDefinition } from './types';

describe('macro research comparability', () => {
  it('allows cross-country identical economic definitions', () => {
    expect(measureFamily('policy_rate.us.bis')).toBe(measureFamily('policy_rate.jp.bis'));
    expect(measureFamily('gdp.real_growth.world')).toBe(measureFamily('gdp.real_growth.cn'));
    expect(semanticallyCompatible(['credit_gap.us.bis','credit_gap.jp.bis'])).toBe(true);
  });
  it('rejects false comparisons even where percentages and frequencies match', () => {
    expect(semanticallyCompatible([
      'labour.world.productivity_growth', 'labour.world.income_share',
    ])).toBe(false);
    expect(semanticallyCompatible([
      'profit.eu27.corporate_operating_surplus_gdp',
      'profit.eu27.nonfinancial_gross_surplus_value_added',
    ])).toBe(false);
    expect(semanticallyCompatible([
      'fiscal.world.public_debt', 'policy_rate.us.bis',
    ])).toBe(false);
    expect(semanticallyCompatible([
      'gold.usd.monthly_average', 'bond.us.real_10y',
    ])).toBe(false);
  });
  it('keeps bad draft pairings out of the main editorial chapters', () => {
    const valid = (id: string, status: 'mapped' | 'draft', ids: string[]): ChartDefinition => ({
      id, status, theme: 'labour_capital', title: id,
      rationale: id, caveats: id, display_mode: 'raw', series_ids: ids,
    });
    const results = curatedCharts([
      valid('world_productivity_labour_income','draft',[
        'labour.world.productivity_growth','labour.world.income_share']),
      valid('world_productivity_growth','mapped',['labour.world.productivity_growth']),
      valid('public_debt_vs_rates','draft',['fiscal.world.public_debt','policy_rate.us.bis']),
    ], ['world_productivity_labour_income','world_productivity_growth','public_debt_vs_rates']);
    expect(results.map(x => x.id)).toEqual(['world_productivity_growth']);
  });
});
