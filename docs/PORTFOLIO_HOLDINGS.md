# Recorded holdings and model scenarios

Use **Portfolio → ETF holdings** to record actual positions. The holdings snapshot is separate from **Model portfolio scenarios**. Importing positions does not select an ACWI/bond/gold model, establish personal historical returns or change the model's example inputs.

## Recording a snapshot

Each position has an account, instrument name, quantity and supplied EUR market value. Optional fields include ISIN, exchange ticker, EUR price, asset classification and an official identity-reference URL. Preserve uncertain identities as unconfirmed. An ISIN must have the correct format and checksum; that check alone does not verify a broker's holding.

Use the observation date of the actual statement. Leave it blank when unknown; the import time is not a valuation date. Contributions and withdrawals also remain unknown when blank. **Listed positions only** does not assert a complete account or portfolio, and cash can be absent. Select full invested-portfolio scope only when that describes the supplied positions.

Account totals are always separate. Explicitly enable account combination to calculate combined weights. Positions with the same exact ISIN can then share an instrument row; names and tickers alone never merge positions. An unresolved share class remains a separate row. The supplied EUR values are authoritative for this snapshot; a quantity-times-price discrepancy produces a warning rather than silently changing a broker value.

Classify a mixed precious-metals product as `precious_metals`, not `gold`. An EUR exchange quote does not establish underlying EUR exposure or currency hedging. Country, issuer and sector look-through requires matching original holdings for the actual fund and period. Published fund examples in P01 are labelled separately.

## Import format

The editor accepts CSV or tab-separated rows with a header. Use plain numbers with a decimal point; normalize locale-specific thousands/decimal separators first. For example, this is synthetic input:

```csv
account,name,quantity,value_eur,isin,price_eur,asset_class
Example account,Unconfirmed equity fund,2,60,,30,equity
```

Import adds an unsaved draft. Review identities and scope before saving. Totals and weights come from Python after validation. Saving uses the loaded revision; a stale update returns a conflict and preserves the draft. Reload the winning server version before applying a new edit.

## Research boundaries and recovery

P01 shows recorded instrument weights independently of the published fund examples. Its original owner-allocation role is supplied only by a dated, fully identified snapshot explicitly declared to cover the invested portfolio. An undated or partial list remains useful without certifying completeness. Current holdings cannot supply ex-ante historical allocations, a missing constituent return history, tax basis, fund duration/convexity or an investment return.

The server stores only this snapshot at `/data/portfolio-holdings.json`, configurable natively with `FINANCE_PORTFOLIO_HOLDINGS`. `GET/PUT /api/portfolio-holdings` use optimistic revisions and atomic, locked writes. Invalid or corrupt existing state is preserved and reported rather than replaced with an empty portfolio. Model inputs remain in `owner-inputs.json`.

Version-2 recovery bundles now include the optional `portfolio_holdings` application-state member. Older bundles that predate holdings cannot restore it. Verify the new bundle and restore with the matching release image into an empty destination, as in [RUNNING.md](RUNNING.md). Private positions belong in the data directory and recovery copies, never in the image, source repository or screenshots committed to git.
