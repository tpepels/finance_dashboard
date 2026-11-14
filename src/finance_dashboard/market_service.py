"""Atomic market/FX ingestion, revisions, and EUR performance from stored prices."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import (
    FxIngestionRun, FxRateVersion, MarketIngestionRun,
    MarketInstrumentRow, MarketPriceVersion, MarketActionVersion, now_utc,
)
from .market import EcbFxClient, MarketDataError, MarketHistory, PriceBar, YahooMarketClient, instruments, performance
from .service import safe_source_failure_code
from .source_policy import PolicyDeferred


def _price_values(row):
    return (row.close, row.adjusted_close, row.volume)


def current_market_prices(session: Session, instrument_id: str,
                          start: date | None = None, end: date | None = None,
                          snapshot_at: datetime | None = None) -> list[MarketPriceVersion]:
    statement = select(MarketPriceVersion).where(MarketPriceVersion.instrument_id == instrument_id)
    if start:
        statement = statement.where(MarketPriceVersion.day >= start)
    if end:
        statement = statement.where(MarketPriceVersion.day <= end)
    if snapshot_at:
        statement = statement.where(MarketPriceVersion.first_seen_at <= snapshot_at)
    rows = session.scalars(statement.order_by(MarketPriceVersion.day, MarketPriceVersion.id.desc()))
    latest = {}
    for row in rows:
        latest.setdefault(row.day, row)
    return list(latest.values())


def current_market_actions(session: Session, instrument_id: str,
                           snapshot_at: datetime | None = None) -> list[MarketActionVersion]:
    statement = select(MarketActionVersion).where(MarketActionVersion.instrument_id == instrument_id)
    if snapshot_at:
        statement = statement.where(MarketActionVersion.first_seen_at <= snapshot_at)
    rows = session.scalars(statement.order_by(MarketActionVersion.id.desc()))
    latest = {}
    for row in rows:
        latest.setdefault((row.ex_date, row.action_type), row)
    return sorted(latest.values(), key=lambda row: (row.ex_date, row.action_type))


def current_fx(session: Session, currency: str, snapshot_at: datetime | None = None) -> dict[date, Decimal]:
    statement = select(FxRateVersion).where(FxRateVersion.currency == currency)
    if snapshot_at:
        statement = statement.where(FxRateVersion.first_seen_at <= snapshot_at)
    rows = session.scalars(statement.order_by(FxRateVersion.day, FxRateVersion.id.desc()))
    values = {}
    for row in rows:
        values.setdefault(row.day, row.foreign_per_eur)
    return values


class MarketIngestionService:
    def __init__(self, engine, market_client=None, fx_client=None, registry=None):
        self.engine = engine
        self.market_client = market_client
        self.fx_client = fx_client
        self.registry = registry if registry is not None else instruments()

    def refresh_instrument(self, instrument_id: str, *, full: bool = False,
                           today: date | None = None) -> dict:
        definition = self.registry.get(instrument_id)
        if not definition:
            raise ValueError(f"Unknown instrument: {instrument_id}")
        with Session(self.engine) as session, session.begin():
            row = session.get(MarketInstrumentRow, instrument_id)
            if row is None:
                session.add(MarketInstrumentRow(
                    id=instrument_id, symbol=definition["source_symbol"],
                    exchange_mic=definition["exchange_mic"],
                    currency=definition["trading_currency"], updated_at=now_utc(),
                ))
            elif ((row.symbol, row.currency, row.exchange_mic) !=
                  (definition["source_symbol"], definition["trading_currency"], definition["exchange_mic"])):
                raise ValueError("Market source mapping changed; explicit migration required")
        with Session(self.engine) as session:
            last_day = session.scalar(select(func.max(MarketPriceVersion.day)).where(
                MarketPriceVersion.instrument_id == instrument_id))
        # Historic dividend/split revisions can alter vendor adjusted closes.
        # Do not truncate the full history on regular refreshes.
        start = None
        run_id = str(uuid4())
        with Session(self.engine) as session, session.begin():
            session.add(MarketIngestionRun(id=run_id, instrument_id=instrument_id,
                  started_at=now_utc(), status="running",
                  requested_from=start, observations_received=0, versions_added=0))
        try:
            source_client = self.market_client or YahooMarketClient()
            try:
                history = source_client.fetch(definition, start=start)
            finally:
                if self.market_client is None:
                    source_client.close()
            if not history.price_bars or history.currency != definition["trading_currency"]:
                raise MarketDataError("Market feed returned wrong currency or no observations")
            if any(day > (today or date.today()) for day in history.price_bars):
                raise MarketDataError("Future-dated market observation")
            with Session(self.engine) as session, session.begin():
                session.execute(select(MarketInstrumentRow).where(
                    MarketInstrumentRow.id == instrument_id).with_for_update()).scalar_one()
                previous = session.scalars(select(MarketPriceVersion).where(
                    MarketPriceVersion.instrument_id == instrument_id).order_by(
                    MarketPriceVersion.id.desc()))
                latest = {}
                for row in previous:
                    latest.setdefault(row.day, _price_values(row))
                action_rows = session.scalars(select(MarketActionVersion).where(
                    MarketActionVersion.instrument_id == instrument_id)
                    .order_by(MarketActionVersion.id.desc()))
                latest_actions = {}
                for action in action_rows:
                    latest_actions.setdefault((action.ex_date, action.action_type), action.value)
                added = 0
                for day, bar in history.price_bars.items():
                    if (not bar.close.is_finite() or bar.close <= 0 or
                            not bar.adjusted_close.is_finite() or bar.adjusted_close <= 0):
                        raise MarketDataError("Invalid market EOD close")
                    values = (bar.close, bar.adjusted_close, bar.volume)
                    if values != latest.get(day):
                        session.add(MarketPriceVersion(
                            instrument_id=instrument_id, day=day, close=bar.close,
                            adjusted_close=bar.adjusted_close, volume=bar.volume,
                            first_seen_at=now_utc(), ingestion_run_id=run_id))
                        added += 1
                for action_type, actions in (("dividend", history.dividends),
                                             ("split", history.splits)):
                    for ex_date, value in actions.items():
                        ident = (ex_date, action_type)
                        if latest_actions.get(ident) != value:
                            session.add(MarketActionVersion(
                                instrument_id=instrument_id, ex_date=ex_date,
                                action_type=action_type, value=value,
                                first_seen_at=now_utc(), ingestion_run_id=run_id))
                            added += 1
                run = session.get(MarketIngestionRun, run_id)
                run.status = "success"
                run.ended_at = now_utc()
                run.observations_received = len(history.price_bars)
                run.versions_added = added
                session.get(MarketInstrumentRow, instrument_id).updated_at = now_utc()
            from .data_change_bus import publish_change
            publish_change(self.engine, "market_ingested")
            return {"instrument_id":instrument_id,"status":"success",
                    "received":len(history.price_bars),"versions_added":added,
                    "dividends":len(history.dividends),"splits":len(history.splits),
                    "latest":max(history.price_bars).isoformat()}
        except Exception as exc:
            with Session(self.engine) as session, session.begin():
                run = session.get(MarketIngestionRun, run_id)
                run.status = "deferred" if isinstance(exc, PolicyDeferred) else "failed"
                run.ended_at = now_utc()
                run.error = safe_source_failure_code(exc)
            raise

    def refresh_fx(self, currency: str, *, full: bool = False) -> dict:
        if currency not in ("USD","GBP","CHF"):
            raise ValueError("Currency unsupported")
        with Session(self.engine) as session:
            latest = session.scalar(select(func.max(FxRateVersion.day)).where(
                FxRateVersion.currency == currency))
        start = None if full or latest is None else latest-timedelta(days=30)
        run_id = str(uuid4())
        with Session(self.engine) as session, session.begin():
            session.add(FxIngestionRun(id=run_id,currency=currency,started_at=now_utc(),
                status="running",observations_received=0,versions_added=0))
        try:
            fx_source = self.fx_client or EcbFxClient()
            try:
                values = fx_source.fetch(currency,start)
            finally:
                if self.fx_client is None:
                    fx_source.close()
            if not values:
                raise MarketDataError("ECB FX response empty")
            with Session(self.engine) as session, session.begin():
                rows = session.scalars(select(FxRateVersion).where(
                    FxRateVersion.currency == currency).order_by(FxRateVersion.id.desc()))
                previous = {}
                for row in rows:
                    previous.setdefault(row.day,row.foreign_per_eur)
                added=0
                for day,value in values.items():
                    if day > date.today() or not value.is_finite() or value <= 0:
                        raise MarketDataError("Invalid ECB FX period or value")
                    if previous.get(day) != value:
                        session.add(FxRateVersion(
                            currency=currency,day=day,foreign_per_eur=value,
                            first_seen_at=now_utc(),ingestion_run_id=run_id))
                        added+=1
                run=session.get(FxIngestionRun,run_id)
                run.status="success"
                run.ended_at=now_utc()
                run.observations_received=len(values)
                run.versions_added=added
            from .data_change_bus import publish_change
            publish_change(self.engine, "fx_ingested")
            return {"currency":currency,"status":"success","received":len(values),
                    "versions_added":added}
        except Exception as exc:
            with Session(self.engine) as session, session.begin():
                run=session.get(FxIngestionRun,run_id)
                run.status="deferred" if isinstance(exc, PolicyDeferred) else "failed"
                run.ended_at=now_utc()
                run.error=safe_source_failure_code(exc)
            raise

    def read_performance(self, instrument_id: str, *,
                         start: date | None = None, end: date | None = None,
                         snapshot_at: datetime | None = None) -> dict:
        definition=self.registry.get(instrument_id)
        if definition is None:
            raise ValueError(f"Unknown instrument: {instrument_id}")
        with Session(self.engine) as session:
            # Full pre-window history is required to normalize price and return
            # indices to a consistent inception/base point before filtering.
            rows=current_market_prices(session,instrument_id,end=end,snapshot_at=snapshot_at)
            actions=current_market_actions(session,instrument_id,snapshot_at=snapshot_at)
            fx=current_fx(session,definition["trading_currency"],snapshot_at=snapshot_at)
        if not rows:
            return {"instrument_id":instrument_id,"status":"no_data","observations":[]}
        bars={row.day: PriceBar(row.day,row.close,row.adjusted_close,row.volume) for row in rows}
        dividends={row.ex_date:row.value for row in actions if row.action_type == "dividend"
                   and row.ex_date <= max(bars)}
        splits={row.ex_date:row.value for row in actions if row.action_type == "split"
                and row.ex_date <= max(bars)}
        history=MarketHistory(definition["source_symbol"],definition["trading_currency"],
            bars,dividends,splits,f"https://query1.finance.yahoo.com/v8/finance/chart/{definition['source_symbol']}")
        dataset=performance(history,fx)
        dataset["instrument_id"]=instrument_id
        dataset["name"]=definition["name"]
        dataset["source_url"]=definition["reference_url"]
        dataset["status"]="ready"
        dataset["quote_exchange"]=definition["exchange_mic"]
        dataset["isin"]=definition["isin"]
        dataset["distribution_policy"]=definition["distribution_policy"]
        if start:
            dataset["observations"]=[row for row in dataset["observations"]
                                     if row["date"]>=start.isoformat()]
        return dataset
