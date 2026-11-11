// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Workbench from './Workbench';

const rows = [
  { analysis_id: 'M02', question: 'What is driving bond yields?', decision_informed: 'Duration and inflation-linked bonds.',
    sources: ['Federal Reserve H.15 Selected Interest Rates'], geographies: ['US'], state: 'accepted', has_engine: true },
  { analysis_id: 'L04', question: 'How sensitive are Marxian surplus estimates?', decision_informed: 'Political-economy research.',
    sources: ['Rotta & Kumar (2024)'], geographies: ['WORLD'], state: 'conditional', has_engine: true },
  { analysis_id: 'G03', question: 'How large are listed-company profits?', decision_informed: 'Global profit geography.',
    sources: ['MSCI'], geographies: ['WLD'], state: 'deferred', has_engine: true },
];

describe('Workbench', () => {
  afterEach(() => cleanup());

  it('finds a question by words, topic and region, and links to it', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(rows)))));
    const user = userEvent.setup();
    render(<Workbench/>);
    expect(await screen.findByText('What is driving bond yields?')).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    await user.type(screen.getByRole('searchbox', { name: /find a question/i }), 'inflation');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    await user.clear(screen.getByRole('searchbox', { name: /find a question/i }));
    await user.click(screen.getByRole('button', { name: 'Labour & inequality' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByRole('link', { name: /marxian/i }).getAttribute('href')).toBe('#q-L04');
    await user.click(screen.getByRole('button', { name: 'All topics' }));
    await user.selectOptions(screen.getByLabelText('Region'), 'US');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('accepted', { selector: 'span.workbench-state' })).toBeTruthy();
  });

  it('says plainly when nothing matches', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(rows)))));
    const user = userEvent.setup();
    render(<Workbench/>);
    await screen.findByText('What is driving bond yields?');
    await user.type(screen.getByRole('searchbox', { name: /find a question/i }), 'zzzz');
    expect(screen.getByText(/no question matches/i)).toBeTruthy();
  });

  it('filters the evaluated research state without treating alternatives as accepted', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      evaluated_at: '2026-11-11T12:00:00Z', counts: { accepted: 1, conditional: 1, deferred: 1 },
      questions: rows.map(row => ({ ...row, phase2: { state: row.state, evaluated_at: '2026-11-11T12:00:00Z',
        limitations: [], open_gates: row.state === 'deferred' ? ['original coverage missing'] : [], verified_alternatives: [] } })),
    })))));
    const user = userEvent.setup();
    render(<Workbench/>);
    await screen.findByText('What is driving bond yields?');
    await user.selectOptions(screen.getByLabelText('Research state'), 'deferred');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByRole('link', { name: /listed-company profits/ })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /bond yields/ })).toBeNull();
  });

  it('offers a retry when the research catalogue cannot be read', async () => {
    let available = false;
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(available
      ? new Response(JSON.stringify({ questions: rows })) : new Response('{}', { status: 500 }))));
    const user = userEvent.setup();
    render(<Workbench/>);
    await screen.findByRole('alert');
    available = true;
    await user.click(screen.getByRole('button', { name: 'Retry research status' }));
    expect(await screen.findByRole('link', { name: /bond yields/ })).toBeTruthy();
  });
});
