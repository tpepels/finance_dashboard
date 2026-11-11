# Portfolio calculation validation

Validation date: 2026-11-11. The checks below assess software arithmetic and failure handling using controlled fixtures. They do not establish the current research installation's source acceptance, validate a predictive strategy, or represent owner approval of the graphics. Work was performed in the isolated completion worktree, based on revision `2bd3e4f30e2281dff8f86fc14c858b83733a618a`, with uncommitted completion changes and Python 3.12.15. No original owner data or research data directory was used.

Two defects were reproduced before their fixes:

- Owner validation accepted some nonfinite monetary values, silently converted strings such as `"false"` to true, truncated fractional rebalancing months, and leaked generic exceptions for malformed objects. Validation now rejects these with `OwnerInputError` and preserves an existing saved file byte for byte. A malformed saved file remains untouched and loads an explicitly labelled example.
- P07 real wealth compounded observed returns across a missing inflation period, while its real statistics used only the latest contiguous inflation-observed run. The real wealth path now uses that same run. Nominal wealth continues over its independently supported nominal history.

## Independent numerical examples

Expected values below are literal arithmetic, separate from production helpers. Existing golden endpoint comparisons remain useful compatibility checks, but are not independent numerical validation.

| Check | Hand calculation and expected result | Automated evidence |
|---|---|---|
| 60/40 replay, zero costs and flows | 60 × 1.10 + 40 × 0.90 = **102** from 100 | `test_engine_owner.py` |
| Equity shock | 60% weight × −20% = **−12 percentage points** of portfolio value | `test_engine_owner.py` |
| Duration shock | Duration 7 × +1 pp yield change gives **−7%** for an all-bond holding and **−2.8 pp** at 40% bond weight | `test_engine_owner.py` |
| Calendar, threshold and never rules | After the first replay above, equity is 66 of 102, a 4.706 pp drift. A 5 pp band holds; a 4 pp band rebalances. A one-month calendar trades; a two-month calendar does not yet trade; never does not trade | `test_engine_owner.py` |
| Trading costs | Target equity 61.2 implies a 4.8 sale and 4.8 bond purchase. One-sided turnover 4.8 × 100 bps = **0.048**; remaining wealth **101.952** | `test_engine_owner.py` |
| Contribution and withdrawal timing | 100 × 1.10 + 10 contribution = 120; 12% annual withdrawal means 1% of current value that month, leaving **118.8** | `test_engine_owner.py` |
| Contribution cost basis | Begin 50/50; equity doubles in month 1; add 100 split 50/50 each month for two months. Before the month-2 rebalance, equity is 200 with basis 150 and bonds are 150. Selling 25 realises 6.25; 25% tax is **1.5625**, leaving **348.4375** | `test_engine_owner.py` |
| Withdrawal gain share | A 100 equity holding doubles to 200. A 10 withdrawal sells 5 of gain and 5 of basis. The simplified 25% gain charge is **1.25**, leaving **188.75** | `test_engine_owner.py` |
| Losses and exhausted capital | A loss has no tax credit. A complete asset loss leaves wealth **0**; subsequent returns, percentage withdrawals, annual value tax and calendar rebalancing do not create wealth or divide by zero | `test_engine_owner.py` |
| Annual value tax | On an unchanged 100 holding, 2% after each 12 replay months charges **2** then **1.96**, leaving **96.04** after 24 months | `test_engine_owner.py` |
| P05 native USD returns and FX | Equity 100→120 USD with USD/EUR 2→3 loses 20% in EUR. A native bond return 0.05 means 5%, losing 30% in EUR. A 60/40 mix ends at **76** | `test_engine_owner.py` |
| P07 FX, carry and real wealth | The same equity and FX imply −20% unhedged. Start-month EUR/US rates 0%/12% imply −1% monthly carry: hedged growth is 1.2 × 0.99 = 1.188. With 10% inflation, real growth is **1.08** | `test_engine_p07.py` |
| Gaps | Missing March equity levels leave only the May return in P05's final run. Missing March HICP leaves only May in P07 real wealth and statistics, with nominal wealth retained. P06 gets no outcome window from an incomplete or gapped horizon | `test_engine_owner.py`, `test_engine_p07.py`, `test_engine_p06_f03.py` |
| P06 native yield units | 5% earnings yield becomes **0.05**; 4% nominal less 1.5% real yield gives **0.025** breakeven. A 4% nominal yield deflated by 10% trailing inflation gives **−0.05454545…** | `test_engine_p06_f03.py` |

Duration is a first-order approximation. These shock examples exclude convexity, changing duration, correlated shocks and simultaneous market responses.

## Replay accounting conventions and limits

For each month, P05 applies asset returns, adds the contribution at target weights and to cost basis, then withdraws one twelfth of the entered annual percentage of current portfolio value. A tax on value is charged every 12 replay months, rather than at the end of each calendar year. The selected calendar or threshold rule then rebalances; trading costs and any tax on the primary realised gain are deducted afterward. Thresholds trigger only when drift is strictly greater than the chosen band.

Trading costs use one-sided turnover, half the sum of absolute changes in holdings. Contributions and withdrawals do not incur the entered trading cost. Primary sales use proportional average cost basis. Losses have no tax credit or carryforward. Fees and tax funding use simplified reductions in holdings and basis, without recursively taxing gains realised to pay those charges. The numerical tests establish this disclosed simplified convention; they do not establish tax-law correctness. The model excludes allowances, jurisdiction-specific rules, fund fees, slippage and tracking differences.

Withdrawals are percentages of current wealth, not fixed euro spending. Within the valid owner-input range, a monthly percentage withdrawal alone does not exhaust positive capital in finite exact arithmetic. The exhaustion test therefore uses a complete market loss and verifies that subsequent withdrawals and taxes remain safe. Fixed-spending depletion and investor-level cash-flow-adjusted return statistics are outside this model. Reported wealth and drawdown include contributions and withdrawals.

P04 uses the owner's equity hedge share, euro-area equity share and duration for isolated sensitivities. P05 always replays the USD ACWI equity index translated unhedged into EUR. Those three P04 inputs do not alter the replay. Selecting euro or hedged bonds selects a reconstructed German 10-year par-bond history, rather than calculating an actual currency hedge on the US bond history. The bond surrogate has its own duration and is not the owner's specific fund. These distinctions, transaction order and simplified tax funding appear in P05 bundle method limitations and text exports, with a bundle/export regression test.

## Source reconciliation and sample scope

The existing return-original reconciliation tests independently read selected archived originals using acquisition receipts, check original and manifest hashes, require native units and source identity, and reject missing, altered, empty or mismatched evidence. Their fixtures distinguish French market excess returns from total returns and percent units from Swinkels ratio units. The par-bond test checks two literal published Swinkels values, and verifies that a missing month breaks the chain. The new P05 arithmetic test then checks that native ratio returns and USD-per-EUR FX are translated in the correct direction without a percent-scale error.

These are fixture-based software checks. They do not reconcile the current installation's selected source histories, benchmark alternatives, sampled years or latest revisions. A current release assessment must record the selected source receipts/hashes, native dates and units, current acceptance gates and actual common replay window. The replay selects the latest contiguous common run among positive-weight assets; gaps and differing source endpoints can shorten that run. Neither history nor missing months are extended synthetically. P06's global earnings-yield role must remain subject to the separate empirical readiness assessment; these tests do not close an unresolved source gate.

P07 hedging is the start-month ECB deposit-facility/effective federal-funds rate difference divided by 1200, multiplied into USD equity growth. It omits forward basis, actual hedge transactions and fund expenses. ECB reference FX rates are not transaction rates. Real statistics and wealth additionally require adjacent observed HICP levels, and can cover a shorter run than nominal results.

P06 uses latest revised valuation/return histories and overlapping outcome windows. The tests establish arithmetic, units and gap handling. They do not provide as-known-then evidence, nonoverlapping holdout samples, predictive accuracy or calibrated uncertainty for a future allocation. Its ranges retain their stated model-based planning interpretation; historical replay remains descriptive and does not establish an investment timing signal.

## Verification and outstanding acceptance

Focused checks pass with the following reproducible invocations from the completion worktree. `PYTHONPATH=src` ensures that the shared virtual environment imports this worktree:

```sh
rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_owner_inputs.py
rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_owner_inputs_api.py
rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_engine_owner.py
rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_engine_p06_f03.py
rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_engine_p07.py
rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_return_source_reconciliation.py
```

The individual runs cover 8, 3, 18, 9, 11 and 8 test methods respectively. The owner-input and P07 regressions were observed failing before their fixes; the new P05 disclosure test also failed before the method register was extended. An initial broader engine run passed 165 tests and failed to import the in-progress `test_engine_views` because `engine/views.py` was not yet present. Full offline discovery then ran 1,140 tests in 31.4 seconds with the same single import error and 10 optional skips; its command was `rtk proxy env PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`. Final integrated suite results belong to the release verification record after the parallel implementation is complete. FastAPI test-client runs emit an upstream Starlette/httpx deprecation warning.

Still required: the release's current-corpus assessment; owner review of P04/P05/P06/P07 graphics, input meaning, limitations and exact-view exports; and any actual server/second-device checks. This report supplies no visual approval or remote-access evidence and does not mark those gates complete.
