"""Independent figure views retain scientific gates and reproducible arithmetic."""
from datetime import date
import unittest

from finance_dashboard.engine.views import figure_capabilities, render_figure, validate_view


class FigureViewTests(unittest.TestCase):
    def test_fx_quote_units_are_never_grouped_on_a_native_axis(self):
        for f in figure_capabilities('M04')['figures']:
            fx = [r for r in f['roles'] if r['series_id'].startswith('fx.')]
            self.assertLessEqual(len(fx), 1, f)

    def test_derived_cadence_and_structured_windows_do_not_make_false_promises(self):
        bundle = {'values': {'history': {'DE': [['2020-01-01',100],['2020-04-01',110]]}}}
        caps = figure_capabilities('C01', bundle=bundle)
        derived = next(f for f in caps['figures'] if f['id']=='result:history/DE')
        self.assertNotIn('line', derived['encodings'])
        table = next(f for f in caps['figures'] if f['id']=='result:table')
        with self.assertRaises(ValueError):
            validate_view('C01', {**table['defaults'], 'start':'2020'}, capabilities=caps)

    def test_country_filter_and_visible_base_are_independent(self):
        cap = figure_capabilities('C01')
        figure = next(f for f in cap['figures'] if any(r['id'] == 'cli:DE' for r in f['roles']))
        spec = validate_view('C01', {**figure['defaults'], 'geographies': ['DE'],
                                   'start': '2020-02-01', 'transform': 'index_100'})
        points = {'cli:DE': [(date(2020, 1, 1), 50), (date(2020, 2, 1), 100), (date(2020, 4, 1), 120)],
                  'cli:US': [(date(2020, 2, 1), 80)]}
        result = render_figure('C01', spec, points, {'basis': {'kind': 'original'}, 'inputs': []})
        self.assertEqual([s['id'] for s in result['series']], ['cli:DE'])
        self.assertEqual(result['series'][0]['data'], [['2020-02-01', 100.0], ['2020-03-01', None], ['2020-04-01', 120.0]])
        self.assertEqual(points['cli:US'][0][1], 80)

    def test_unsupported_geography_units_and_invalid_log_are_refused(self):
        cap = figure_capabilities('C01')['figures'][0]
        with self.assertRaises(ValueError): validate_view('C01', {**cap['defaults'], 'geographies': ['MARS']})
        with self.assertRaises(ValueError): validate_view('C01', {**cap['defaults'], 'encoding': 'stacked'})
        with self.assertRaises(ValueError): validate_view('C01', {**cap['defaults'], 'start': '2021-01-01', 'end': '2020-01-01'})
        spec = validate_view('C01', {**cap['defaults'], 'scale': 'log'})
        with self.assertRaises(ValueError):
            render_figure('C01', spec, {'cli:US': [(date(2020, 1, 1), 0)]}, {'basis': {'kind': 'original'}})

    def test_unaccepted_analysis_cannot_leak_values_through_a_custom_view(self):
        f = figure_capabilities('C01')['figures'][0]
        spec = validate_view('C01', f['defaults'])
        result = render_figure('C01', spec, {'cli:US': [(date(2020, 1, 1), 99)]}, {'basis': None})
        self.assertEqual(result['series'], [])

    def test_growth_uses_prior_observation_outside_window_without_filling_gap(self):
        f = next(f for f in figure_capabilities('C01')['figures'] if any(r['id']=='cli:US' for r in f['roles']))
        spec = validate_view('C01', {**f['defaults'], 'roles': ['cli:US'], 'start': '2021-01-01', 'transform': 'yoy'})
        points={'cli:US': [(date(2020, 1, 1), 100), (date(2021, 1, 1), 110), (date(2021, 3, 1), 120)]}
        series=render_figure('C01', spec, points, {'basis': {'kind': 'original'}})['series'][0]
        self.assertAlmostEqual(series['data'][0][1], 10)
        self.assertEqual(len(series['data']), 1)

    def test_native_period_windows_and_independent_event_scope(self):
        f = figure_capabilities('C01')['figures'][0]
        spec = validate_view('C01', {**f['defaults'], 'start': '2020-Q1', 'end': '2020-04', 'events': ['covid_shock']})
        self.assertEqual((spec.start, spec.end), ('2020-01-01', '2020-04-30'))
        result = render_figure('C01', spec, {}, {'basis': {'kind': 'original'}},
            recessions=[{'start':'2020-03-01','end':'2020-04-30'}])
        self.assertEqual([e['id'] for e in result['events']], ['covid_shock'])
        self.assertEqual(result['events'][0]['start'], '2020-01-30')


if __name__ == '__main__': unittest.main()
