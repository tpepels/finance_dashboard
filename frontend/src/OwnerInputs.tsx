import { useEffect, useState, type FormEvent } from 'react';

type Inputs = {
  allocation: { equity: number; bonds: number; gold: number };
  equity_hedged_share: number; equity_euro_share: number; bonds_hedged: boolean; bond_duration_years: number;
  rebalancing: { rule: 'never' | 'calendar' | 'threshold'; months: number; band_pp: number };
  trading_cost_bps: number; start_value_eur: number; monthly_contribution_eur: number; annual_withdrawal_pct: number;
  tax: { mode: 'none' | 'realised_gains' | 'yearly_on_value'; rate_pct: number }; is_example?: boolean;
};

const percent = (v: number) => String(Math.round(v * 1000) / 10);

function Field({ label, value, onChange, step = 1, suffix }: { label: string; value: string; onChange: (v: string) => void;
  step?: number; suffix?: string }) {
  const id = `owner-${label.replace(/\W+/g, '-').toLowerCase()}`;
  return <div className="owner-field">
    <label htmlFor={id}>{label}</label>
    <input id={id} type="number" inputMode="decimal" step={step} value={value} onChange={e => onChange(e.target.value)}/>
    {suffix && <span className="owner-suffix">{suffix}</span>}
  </div>;
}

/** The owner's portfolio parameters: a local form whose saved values feed the portfolio analyses (P04, P05). */
export default function OwnerInputs() {
  const [form, setForm] = useState<Record<string, string>>({});
  const [rule, setRule] = useState<Inputs['rebalancing']['rule']>('threshold');
  const [hedgedBonds, setHedgedBonds] = useState(true);
  const [taxMode, setTaxMode] = useState<Inputs['tax']['mode']>('none');
  const [example, setExample] = useState<boolean | null>(null);
  const [status, setStatus] = useState<{ kind: 'saved' | 'error'; text: string } | null>(null);

  const fill = (d: Inputs) => {
    setForm({ equity: percent(d.allocation.equity), bonds: percent(d.allocation.bonds), gold: percent(d.allocation.gold),
      hedged: percent(d.equity_hedged_share), euro: percent(d.equity_euro_share), duration: String(d.bond_duration_years),
      months: String(d.rebalancing.months), band: String(d.rebalancing.band_pp), cost: String(d.trading_cost_bps),
      start: String(d.start_value_eur), contribution: String(d.monthly_contribution_eur), withdrawal: percent(d.annual_withdrawal_pct),
      taxRate: String(d.tax?.rate_pct ?? 0) });
    setTaxMode(d.tax?.mode ?? 'none');
    setRule(d.rebalancing.rule);
    setHedgedBonds(d.bonds_hedged);
    setExample(Boolean(d.is_example));
  };

  useEffect(() => {
    fetch('/api/owner-inputs', { cache: 'no-store' }).then(r => r.json()).then(fill).catch(() => setStatus({ kind: 'error',
      text: 'Your saved portfolio could not be loaded; the analyses use the example portfolio.' }));
  }, []);

  const set = (key: string) => (value: string) => setForm(f => ({ ...f, [key]: value }));
  const num = (key: string) => Number(form[key] ?? 0);
  const total = num('equity') + num('bonds') + num('gold');

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const body = { allocation: { equity: num('equity') / 100, bonds: num('bonds') / 100, gold: num('gold') / 100 },
      equity_hedged_share: num('hedged') / 100, equity_euro_share: num('euro') / 100, bonds_hedged: hedgedBonds,
      bond_duration_years: num('duration'), rebalancing: { rule, months: num('months'), band_pp: num('band') },
      trading_cost_bps: num('cost'), start_value_eur: num('start'), monthly_contribution_eur: num('contribution'),
      annual_withdrawal_pct: num('withdrawal') / 100, tax: { mode: taxMode, rate_pct: num('taxRate') } };
    const response = await fetch('/api/owner-inputs', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus({ kind: 'error', text: `Not saved: ${(data as { detail?: string }).detail ?? 'the server refused these inputs'}.` });
      return;
    }
    fill(data as Inputs);
    setStatus({ kind: 'saved', text: 'Saved. The portfolio analyses now use your figures.' });
    window.dispatchEvent(new Event('gcm-data-updated'));
  };

  if (example === null && !status) return null;
  return <section className="decision-section owner-inputs" aria-labelledby="owner-inputs-title">
    <header className="decision-section-head">
      <h3 id="owner-inputs-title">Your portfolio</h3>
      <p>{example ? 'The analyses below use an example portfolio until you save your own figures.'
        : 'The analyses below use the figures you saved.'} They are stored only on this machine.</p>
    </header>
    <form className="owner-form" onSubmit={save}>
      <fieldset>
        <legend>Mix <span className={Math.abs(total - 100) < 0.1 ? 'owner-total' : 'owner-total owner-total-off'}>{total.toFixed(0)}% of 100%</span></legend>
        <Field label="Equities (%)" value={form.equity ?? ''} onChange={set('equity')}/>
        <Field label="Bonds (%)" value={form.bonds ?? ''} onChange={set('bonds')}/>
        <Field label="Gold (%)" value={form.gold ?? ''} onChange={set('gold')}/>
      </fieldset>
      <fieldset>
        <legend>Currency and bonds</legend>
        <Field label="Euro-area share of equities (%)" value={form.euro ?? ''} onChange={set('euro')}/>
        <Field label="Foreign equities hedged to euro (%)" value={form.hedged ?? ''} onChange={set('hedged')}/>
        <Field label="Bond duration (years)" value={form.duration ?? ''} onChange={set('duration')} step={0.1}/>
        <div className="owner-field owner-check">
          <input id="owner-bonds-hedged" type="checkbox" checked={hedgedBonds} onChange={e => setHedgedBonds(e.target.checked)}/>
          <label htmlFor="owner-bonds-hedged">Bonds are euro or hedged to euro</label>
        </div>
      </fieldset>
      <fieldset>
        <legend>Rebalancing and costs</legend>
        <div className="owner-field">
          <label htmlFor="owner-rule">Rule</label>
          <select id="owner-rule" value={rule} onChange={e => setRule(e.target.value as Inputs['rebalancing']['rule'])}>
            <option value="never">Never rebalance</option>
            <option value="calendar">On a calendar</option>
            <option value="threshold">When a weight drifts</option>
          </select>
        </div>
        <Field label="Every (months)" value={form.months ?? ''} onChange={set('months')}/>
        <Field label="Drift band (points)" value={form.band ?? ''} onChange={set('band')} step={0.5}/>
        <Field label="Trading cost (basis points)" value={form.cost ?? ''} onChange={set('cost')}/>
      </fieldset>
      <fieldset>
        <legend>Money in and out</legend>
        <Field label="Starting value (€)" value={form.start ?? ''} onChange={set('start')} step={1000}/>
        <Field label="Monthly contribution (€)" value={form.contribution ?? ''} onChange={set('contribution')} step={50}/>
        <Field label="Yearly withdrawal (% of value)" value={form.withdrawal ?? ''} onChange={set('withdrawal')} step={0.5}/>
      </fieldset>
      <fieldset>
        <legend>Tax</legend>
        <div className="owner-field">
          <label htmlFor="owner-tax">Tax</label>
          <select id="owner-tax" value={taxMode} onChange={e => setTaxMode(e.target.value as Inputs['tax']['mode'])}>
            <option value="none">Not modelled</option>
            <option value="realised_gains">On realised gains</option>
            <option value="yearly_on_value">Yearly on value</option>
          </select>
        </div>
        <Field label="Tax rate (%)" value={form.taxRate ?? ''} onChange={set('taxRate')} step={0.1}/>
        <p className="owner-hint">Yearly on value approximates a wealth-based tax such as Dutch box 3 (for example 36% of a deemed
          return of about 6% ≈ 2.2% a year, ignoring the allowance).</p>
      </fieldset>
      <div className="owner-actions">
        <button type="submit">Save my portfolio</button>
        {status && <p role={status.kind === 'error' ? 'alert' : 'status'} className={`owner-status owner-status-${status.kind}`}>{status.text}</p>}
      </div>
    </form>
  </section>;
}
