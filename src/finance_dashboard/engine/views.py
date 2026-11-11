"""Validated independent figures over accepted engine inputs and results.

No browser arithmetic, interpolation, global selection state or executable
expressions enter a view. Native comparisons group the same registered measure,
provider, unit, currency and frequency; derived paths remain separate figures.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import calendar
import math
import re
from os.path import commonprefix

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..catalog import load_documents
from .analyses import DEFINITIONS


class FigureView(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: int = 1
    figure_id: str
    roles: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    currency: str = 'native'
    transform: str = 'level'
    frequency: str = 'native'
    encoding: str = 'line'
    scale: str = 'linear'
    events: list[str] = Field(default_factory=lambda: ['us_recessions'])
    benchmark: str | None = None


def _catalog():
    return {row['id']: row for row in load_documents()[0]['series']}


def _native_figures(analysis_id, catalog):
    definition = DEFINITIONS.get(analysis_id)
    if definition is None:
        raise ValueError('Unknown analysis')
    groups = defaultdict(list)
    for role, sid in definition.inputs.items():
        meta = catalog.get(sid, {})
        bits = sid.split('.')
        # Catalogue country families have a common first and trailing identity.
        # Even matching units never justify grouping distinct measures/providers.
        family = '.'.join([bits[0], '*', *bits[2:]]) if len(bits) > 2 else sid
        if bits[0] == 'fx' or (meta.get('unit') == 'million_local_currency' and not meta.get('currency')):
            family = sid  # Currency/quote dimensions must survive geography grouping.
        identity = (family, meta.get('provider'), meta.get('unit'), meta.get('frequency'), meta.get('currency'))
        groups[identity].append({'id': role, 'label': meta.get('name', role),
            'geography': meta.get('geography', ''), 'series_id': sid})
    figures = []
    for (family, provider, unit, frequency, currency), roles in groups.items():
        figure_id = ':'.join(['input', family, str(provider), str(unit), str(frequency), str(currency)])
        transforms = ['level', 'difference', 'percentile']
        level_unit = unit in {'index', 'usd_per_oz', 'usd', 'million_local_currency',
                             'billion_usd', 'million_eur', 'hours', 'persons', 'thousand_persons'}
        if level_unit:
            transforms += ['index_100', 'yoy']
        encodings = ['line', 'dots', 'small_multiples', 'table']
        if frequency == 'A': encodings.append('bar')
        if family.startswith('policy_rate.'): encodings.append('step')
        if len(roles) > 1: encodings += ['scatter', 'heatmap']
        event_ids = ['us_recessions', 'covid_shock']
        labels = [r['label'] for r in roles]
        prefix = commonprefix(labels)
        suffix = commonprefix([label[::-1] for label in labels])[::-1]
        suffix = suffix[max(0, len(prefix) + len(suffix) - min(map(len, labels))):]
        comparison_label = (prefix.rstrip(' ,;') + ' ' + suffix.lstrip(' ,;')).strip() or 'Same-measure country comparison'
        figures.append({'id': figure_id, 'label': roles[0]['label'] if len(roles) == 1 else comparison_label + ' — by geography',
            'unit': unit or 'native publisher units', 'frequency': frequency, 'roles': roles,
            'geographies': sorted({r['geography'] for r in roles if r['geography']}),
            'encodings': encodings, 'transforms': transforms, 'currencies': ['native'],
            'frequencies': ['native'], 'scales': ['linear', 'log'] if level_unit else ['linear'],
            'events': event_ids, 'source_kind': 'input',
            'unavailable': [{'choice': 'stacked', 'reason': 'These observations are not declared additive contributions.'},
                            {'choice': 'currency conversion', 'reason': 'Use the named EUR-return analysis; an arbitrary exchange conversion would change this measure.'},
                            {'choice': 'frequency conversion', 'reason': 'This figure retains its native observed frequency.'},
                            {'choice': 'covid_recovery', 'reason': 'Recovery requires an explicit series-specific threshold; it is not a recession interval.'}]})
    return figures


def _period(value):
    if not isinstance(value, str): return None
    try:
        if re.fullmatch(r'\d{4}', value): return date(int(value), 1, 1)
        if re.fullmatch(r'\d{4}-\d{2}', value): return date.fromisoformat(value + '-01')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): return date.fromisoformat(value)
    except ValueError:
        pass
    return None


def _derived_series(values, path=()):
    """Discover already-computed individual time series, never combine units.

    Each path is its own figure: two numeric metrics sharing a container are
    not evidence of comparability. Curated reference graphics remain intact.
    """
    if isinstance(values, list) and values and all(
            isinstance(row, (list, tuple)) and len(row) == 2 and _period(row[0])
            and (row[1] is None or type(row[1]) in (int, float)) for row in values):
        yield path, values
    elif isinstance(values, dict):
        for key, value in values.items():
            yield from _derived_series(value, (*path, str(key)))


def _computed_figures(bundle):
    figures = []
    for path, points in _derived_series(bundle.get('values')):
        key = '/'.join(path)
        # A derived quantity retains its exact named metric. It is not silently
        # rescaled to percent or treated as additive with a different metric.
        label = ' · '.join(p.replace('_', ' ') for p in path)
        figures.append({'id': 'result:' + key, 'label': label, 'unit': label + ' (as defined in Method)',
            'frequency': 'native', 'roles': [{'id': key, 'label': label, 'geography': ''}],
            'geographies': [], 'encodings': ['dots', 'table'],
            'transforms': ['level'], 'currencies': ['native'], 'frequencies': ['native'],
            'scales': ['linear'], 'events': ['us_recessions', 'covid_shock'],
            'source_kind': 'result', 'path': list(path),
            'unavailable': [{'choice': 'additional transform', 'reason': 'This result already applies its named method. Change a native input figure for additional supported transforms.'}]})
    # Archive-based questions may only have structured snapshots/estimates.
    # Preserve their complete data as a table rather than inventing a shared
    # numeric axis for unlike concepts.
    figures.append({'id': 'result:table', 'label': 'Complete analytical result', 'unit': 'See the named metric and Method',
        'frequency': 'native', 'roles': [], 'geographies': [], 'encodings': ['table'], 'transforms': ['level'],
        'currencies': ['native'], 'frequencies': ['native'], 'scales': ['linear'], 'events': [],
        'source_kind': 'table', 'unavailable': [{'choice': 'shared chart axis',
          'reason': 'This structured result contains different measurements. Use the curated graphic or an individual native figure.'}]})
    return figures


def figure_capabilities(analysis_id: str, catalog_series=None, bundle=None) -> dict:
    figures = _native_figures(analysis_id, catalog_series or _catalog())
    if bundle is not None: figures += _computed_figures(bundle)
    for figure in figures:
        figure['supports_periods'] = figure['source_kind'] != 'table'
        figure['defaults'] = FigureView(figure_id=figure['id'], encoding=figure['encodings'][0],
            events=['us_recessions'] if 'us_recessions' in figure['events'] else []).model_dump()
    return {'analysis_id': analysis_id, 'method_version': '1', 'figures': figures}


def validate_view(analysis_id: str, raw: dict, *, capabilities=None) -> FigureView:
    try:
        view = FigureView.model_validate(raw)
    except ValidationError as exc:
        raise ValueError('Invalid figure specification: ' + '; '.join(e['msg'] for e in exc.errors())) from None
    if view.version != 1: raise ValueError('Unsupported figure specification version')
    caps = capabilities or figure_capabilities(analysis_id)
    figure = next((f for f in caps['figures'] if f['id'] == view.figure_id), None)
    if figure is None: raise ValueError('This figure is unavailable; restore its method default')
    for chosen, allowed, name in [(view.roles, [r['id'] for r in figure['roles']], 'series'),
                                  (view.geographies, figure['geographies'], 'geography'),
                                  (view.events, figure['events'], 'event')]:
        if len(chosen) != len(set(chosen)) or any(value not in allowed for value in chosen):
            raise ValueError(f'Unsupported or duplicate {name} in this figure')
    for name, choices in [('encoding', 'encodings'), ('transform', 'transforms'), ('currency', 'currencies'),
                           ('frequency', 'frequencies'), ('scale', 'scales')]:
        if getattr(view, name) not in figure[choices]:
            raise ValueError(f'Unsupported {name} for this measure; inspect the available choices')
    if view.benchmark is not None: raise ValueError('This figure has no declared compatible benchmark')
    view.start = _boundary(view.start, end=False)
    view.end = _boundary(view.end, end=True)
    if not figure.get('supports_periods', True) and (view.start or view.end):
        raise ValueError('This complete structured result has no defined date filter; use its native time-series figure')
    if view.start and view.end and view.start > view.end: raise ValueError('Start date must not be after end date')
    if view.scale == 'log' and view.transform in {'difference', 'yoy', 'percentile'}:
        raise ValueError('Log scale is unavailable for this transformation')
    return view


def _boundary(value, *, end):
    if value is None: return None
    try:
        if re.fullmatch(r'\d{4}', value):
            return date(int(value), 12 if end else 1, 31 if end else 1).isoformat()
        quarter = re.fullmatch(r'(\d{4})-Q([1-4])', value)
        if quarter:
            year, q = map(int, quarter.groups())
            month = q * 3 if end else q * 3 - 2
            return date(year, month, calendar.monthrange(year, month)[1] if end else 1).isoformat()
        if re.fullmatch(r'\d{4}-\d{2}', value):
            year, month = map(int, value.split('-'))
            return date(year, month, calendar.monthrange(year, month)[1] if end else 1).isoformat()
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    raise ValueError('Use a valid YYYY, YYYY-MM, YYYY-Q1 or YYYY-MM-DD period')


def _transform(points, view):
    clean = [(str(p.isoformat() if isinstance(p, date) else p), float(v)) for p, v in points
             if v is not None and type(v) in (int, float) and math.isfinite(v)]
    clean.sort(key=lambda p: p[0])
    by_period = {_period(p): v for p, v in clean}
    out = []
    for i, (p, value) in enumerate(clean):
        day = _period(p)
        if day is None: continue
        if view.transform == 'yoy':
            try: previous = day.replace(year=day.year - 1)
            except ValueError: previous = day.replace(year=day.year - 1, day=28)
            base = by_period.get(previous)
            if base in (None, 0): continue
            value = 100 * (value / base - 1)
        elif view.transform == 'difference':
            if i == 0: continue
            prior = _period(clean[i-1][0])
            # Difference is between adjacent observed releases, labelled as such;
            # it never creates an observation in an unobserved interval.
            if prior is None: continue
            value -= clean[i-1][1]
        if view.start and day < date.fromisoformat(view.start): continue
        if view.end and day > date.fromisoformat(view.end): continue
        out.append([p, value])
    if view.transform == 'index_100' and out:
        if out[0][1] <= 0: raise ValueError('Index = 100 requires a positive observed visible base')
        base = out[0][1]
        out = [[p, 100*v/base] for p, v in out]
    if view.transform == 'percentile' and out:
        if len(out) < 20: raise ValueError('Own-history percentile needs at least 20 visible observations')
        vals = [v for _, v in out]
        out = [[p, 100*(sum(x < v for x in vals) + .5*sum(x == v for x in vals))/len(vals)] for p, v in out]
    if view.scale == 'log' and any(v <= 0 for _, v in out):
        raise ValueError('Log scale requires strictly positive observed values')
    return out


def _show_gaps(points, frequency):
    """Null geometry separates observed runs; nulls are not observations."""
    out = []
    for i, (period, value) in enumerate(points):
        if i and frequency in {'M', 'Q', 'A'}:
            before = _period(points[i-1][0]); after = _period(period)
            step = {'M': 1, 'Q': 3, 'A': 12}[frequency]
            months = (after.year-before.year)*12 + after.month-before.month
            if months > step:
                y, m = divmod(before.year*12+before.month-1+step, 12)
                out.append([date(y, m+1, 1).isoformat(), None])
        out.append([period, value])
    return out


VIEW_FORMULAS = {
    'level': 'Native observed values; no interpolation or resampling.',
    'index_100': '100 × x[t] / first positive observed value in the selected visible window.',
    'difference': 'x[t] − x[previous observed release]; missing reference periods are not filled.',
    'yoy': '100 × (x[t] / x[same native period one year earlier] − 1); unmatched periods excluded.',
    'percentile': '100 × (count(x < x[t]) + 0.5 × count(x = x[t])) / N in the selected visible sample; N ≥ 20.',
}


def render_figure(analysis_id: str, spec: FigureView, points: dict, bundle: dict, *, capabilities=None, recessions=()) -> dict:
    caps = capabilities or figure_capabilities(analysis_id, bundle=bundle)
    figure = next(f for f in caps['figures'] if f['id'] == spec.figure_id)
    result = {'id': figure['id'], 'label': figure['label'], 'unit': figure['unit'],
              'frequency': figure['frequency'], 'series': [], 'events': [],
              'encoding': spec.encoding, 'scale': spec.scale,
              'formula': VIEW_FORMULAS[spec.transform], 'missingness': 'No filling or interpolation; observations retain their native reference periods.'}
    if not bundle.get('basis'):
        result['unavailable_reason'] = 'This analysis has unresolved evidence gates; no figure values are released.'
        return result
    if figure['source_kind'] == 'table':
        result['table'] = {'values': bundle.get('values'), 'estimates': bundle.get('estimates')}
        return result
    allowed = {row['role'] for row in bundle.get('inputs', []) if row.get('accepted_under')}
    for role in figure['roles']:
        if spec.roles and role['id'] not in spec.roles: continue
        if spec.geographies and role['geography'] not in spec.geographies: continue
        if figure['source_kind'] == 'result':
            data = bundle.get('values')
            for key in figure['path']: data = data[key]
        else:
            if bundle.get('inputs') and role['id'] not in allowed: continue
            data = points.get(role['id'], [])
        plotted = _transform(data, spec)
        if plotted:
            result['series'].append({'id': role['id'], 'label': role['label'],
                                     'geography': role['geography'], 'data': _show_gaps(plotted, figure['frequency'])})
    if spec.encoding == 'scatter' and len(result['series']) != 2:
        raise ValueError('Scatter requires exactly two observed comparable series')
    if spec.roles or spec.geographies:
        if not any((not spec.roles or r['id'] in spec.roles) and (not spec.geographies or r['geography'] in spec.geographies) for r in figure['roles']):
            raise ValueError('Selected series and geographies do not intersect')
    if spec.transform == 'index_100': result['unit'] = 'index, first visible observation = 100'
    elif spec.transform == 'yoy': result['unit'] = '% change over one year'
    elif spec.transform == 'percentile': result['unit'] = 'percentile of selected observed history'
    elif spec.transform == 'difference': result['unit'] = 'change in ' + figure['unit']
    if 'us_recessions' in spec.events:
        result['events'] += [{'id': 'us_recessions', 'label': 'US NBER recession (US context)', 'scope': 'US context',
            'start': r.get('start'), 'end': r.get('end')} for r in recessions]
    if 'covid_shock' in spec.events:
        result['events'].append({'id': 'covid_shock', 'label': 'WHO COVID-19 public-health emergency (global context)',
            'start': '2020-01-30', 'end': '2023-05-05', 'scope': 'Global public-health emergency; neither a recession nor a measured economic recovery',
            'source_url': 'https://www.who.int/europe/emergencies/situations/covid-19'})
    return result
