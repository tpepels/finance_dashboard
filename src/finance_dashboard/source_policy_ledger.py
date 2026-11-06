"""Durable process-safe publisher budgets, concurrency and cooldown ledger."""
from __future__ import annotations
from contextlib import closing
from email.utils import parsedate_to_datetime
import os
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import quote
from uuid import uuid4
from .source_policy_types import Policy, PolicyViolation, PolicyDeferred
from .source_policy_registry import PolicyRegistry

DEFAULT_LEDGER = Path("/data/source-policy/rate-ledger.sqlite3")
DEFAULT_MAX_WAIT_SECONDS = 3.0

class SourcePolicyGate:
    """Atomic cross-process rolling-window reservations and publisher cooldowns.

    The managed HTTP transport enforces these reservations before the request
    leaves the process. Publisher cooldowns survive process restarts; failed
    connections release concurrency leases but still consume request budget.
    """

    def __init__(self, *, registry: PolicyRegistry | None = None,
                 state_path: Path | None = None, clock=None, sleep=None,
                 max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS):
        self.registry = registry or PolicyRegistry()
        self.state_path = Path(state_path) if state_path is not None else Path(
            os.environ.get("FINANCE_SOURCE_POLICY_DB", str(DEFAULT_LEDGER)))
        self.clock = clock or time.time
        self.sleep = sleep or time.sleep
        self.max_wait_seconds = max_wait_seconds
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if self.state_path.is_symlink():
            raise PolicyViolation("ledger", "symlink_state_forbidden")
        connection = sqlite3.connect(str(self.state_path), timeout=15,
                                     isolation_level=None)
        connection.execute("PRAGMA busy_timeout=15000")
        # Schema creation is idempotent, but must not execute DDL on every
        # request. A per-instance lock protects the first simultaneous callers;
        # SQLite itself serializes initialization across different processes.
        if self._schema_ready:
            return connection
        try:
            with self._schema_lock:
                if not self._schema_ready:
                    connection.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                policy_id TEXT NOT NULL, requested_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS requests_by_policy
                ON requests(policy_id, requested_at);
            CREATE TABLE IF NOT EXISTS leases (
                id TEXT PRIMARY KEY, policy_id TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS leases_by_policy
                ON leases(policy_id, expires_at);
            CREATE TABLE IF NOT EXISTS policy_state (
                policy_id TEXT PRIMARY KEY, next_at REAL NOT NULL DEFAULT 0,
                cooldown_until REAL NOT NULL DEFAULT 0,
                last_http_status INTEGER
            );
                    """)
                    self._schema_ready = True
        except BaseException:
            connection.close()
            raise
        return connection

    @staticmethod
    def _availability_blocker(conn: sqlite3.Connection, policy: Policy,
                              now: float) -> PolicyDeferred | None:
        """Shared read-only decision for both diagnostics and real reservations.

        A preflight can become stale immediately. Only reserve() is permitted
        to grant an actual outbound HTTP request.
        """
        rate = policy.rate
        row = conn.execute(
            "SELECT next_at,cooldown_until FROM policy_state "
            "WHERE policy_id = ?", (policy.id,)).fetchone()
        next_at, cooldown = row if row is not None else (0.0, 0.0)
        if cooldown > now:
            return PolicyDeferred(policy.id, "publisher_cooldown", cooldown)
        if next_at > now:
            return PolicyDeferred(policy.id, "minimum_spacing", next_at)
        count, earliest = conn.execute(
            "SELECT COUNT(*), MIN(requested_at) FROM requests "
            "WHERE policy_id = ? AND requested_at > ?",
            (policy.id, now - rate["window_seconds"])).fetchone()
        if count >= rate["limit"]:
            return PolicyDeferred(
                policy.id, "rolling_window_limit",
                earliest + rate["window_seconds"] + 0.001)
        active, lease_end = conn.execute(
            "SELECT COUNT(*), MIN(expires_at) FROM leases "
            "WHERE policy_id = ? AND expires_at > ?", (policy.id, now)
        ).fetchone()
        if active >= rate["max_concurrent"]:
            return PolicyDeferred(policy.id, "concurrency_limit", lease_end)
        return None

    def availability(self, policy_id: str) -> dict:
        """Read-only best-effort publisher preflight; never reserves quota.

        Does not create policy tables, a database, requests or leases. Invalid
        ledger state fails closed. The managed HTTP transport still performs
        all URL, identity and quota enforcement.
        """
        policy = self.registry.by_id.get(policy_id)
        if policy is None:
            raise PolicyViolation("registry", "unknown_publisher_policy")
        # The shared gate restricts technical availability, not licence status.
        # This preflight must agree with PolicyRegistry.check_request.
        acknowledged = {
            value.strip() for value in os.environ.get(
                "FINANCE_SOURCE_POLICY_ACKNOWLEDGED", "").split(",")
            if value.strip()
        }
        if (policy.restrictions["require_direct_network_ack"]
                and policy.id not in acknowledged):
            return {"state": "blocked", "policy_id": policy.id,
                    "reason": "direct_network_origin_not_confirmed",
                    "retry_at": None}
        if self.state_path.is_symlink():
            raise PolicyViolation("ledger", "symlink_state_forbidden")
        if not self.state_path.exists():
            return {"state": "ready", "policy_id": policy.id,
                    "reason": None, "retry_at": None}
        if not self.state_path.is_file():
            raise PolicyViolation("ledger", "policy_state_unreadable")
        uri = "file:" + quote(str(self.state_path.resolve()), safe="/") + "?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=15)) as conn:
                now = self.clock()
                blocker = self._availability_blocker(conn, policy, now)
        except sqlite3.DatabaseError as exc:
            raise PolicyViolation("ledger", "policy_state_unreadable") from exc
        if blocker is None:
            return {"state": "ready", "policy_id": policy.id,
                    "reason": None, "retry_at": None}
        return {"state": "deferred", "policy_id": policy.id,
                "reason": blocker.reason, "retry_at": blocker.retry_at}

    def _reserve_once(self, policy: Policy) -> str:
        now = self.clock()
        rate = policy.rate
        conn = self._connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM leases WHERE expires_at <= ?", (now,))
            conn.execute("DELETE FROM requests WHERE policy_id = ? AND requested_at <= ?",
                         (policy.id, now - rate["window_seconds"]))
            conn.execute(
                "INSERT OR IGNORE INTO policy_state(policy_id) VALUES (?)",
                (policy.id,))
            blocker = self._availability_blocker(conn, policy, now)
            if blocker is not None:
                raise blocker
            lease = uuid4().hex
            conn.execute(
                "INSERT INTO requests(policy_id,requested_at) VALUES (?,?)",
                (policy.id, now))
            conn.execute(
                "INSERT INTO leases(id,policy_id,expires_at) VALUES (?,?,?)",
                (lease, policy.id, now + rate["lease_seconds"]))
            conn.execute(
                "UPDATE policy_state SET next_at = ? WHERE policy_id = ?",
                (now + rate["min_spacing_seconds"], policy.id))
            conn.execute("COMMIT")
            return lease
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def reserve(self, policy: Policy) -> str:
        waited = 0.0
        while True:
            try:
                return self._reserve_once(policy)
            except PolicyDeferred as exc:
                remaining = exc.retry_at - self.clock()
                if (exc.reason not in {"minimum_spacing", "concurrency_limit"}
                        or remaining <= 0 or waited + remaining > self.max_wait_seconds):
                    raise
                self.sleep(remaining)
                waited += remaining

    @staticmethod
    def _retry_after(headers, now: float) -> float:
        raw = headers.get("retry-after", "")
        if raw:
            try:
                seconds = int(raw)
                if seconds >= 0:
                    return now + seconds
            except ValueError:
                try:
                    date = parsedate_to_datetime(raw)
                    if date.tzinfo is not None:
                        return max(now, date.timestamp())
                except (TypeError, ValueError, OverflowError):
                    pass
        return now

    def keepalive(self, lease: str, policy_id: str) -> None:
        """Renew a live download lease; never resurrect an expired reservation."""
        now = self.clock()
        rate = self.registry.by_id[policy_id].rate
        conn = self._connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "UPDATE leases SET expires_at = ? "
                "WHERE id = ? AND policy_id = ? AND expires_at > ?",
                (now + rate["lease_seconds"], lease, policy_id, now))
            if row.rowcount != 1:
                raise PolicyViolation(policy_id, "download_lease_expired")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def release(self, lease: str, policy_id: str, *,
                status: int | None = None, headers=None) -> None:
        conn = self._connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM leases WHERE id = ? AND policy_id = ?",
                         (lease, policy_id))
            if status in (401, 403, 429) or (status is not None and status >= 500):
                rule = self.registry.by_id[policy_id]
                now = self.clock()
                default = (
                    rule.rate["cooldown_429_seconds"] if status == 429 else
                    rule.rate["cooldown_503_seconds"] if status == 503 else
                    rule.rate["cooldown_access_denied_seconds"]
                    if status in (401, 403) else
                    rule.rate["cooldown_other_5xx_seconds"])
                after = self._retry_after(headers or {}, now)
                until = max(now + default, after)
                conn.execute(
                    "INSERT INTO policy_state(policy_id, cooldown_until, "
                    "last_http_status) VALUES (?,?,?) "
                    "ON CONFLICT(policy_id) DO UPDATE SET "
                    "cooldown_until=MAX(policy_state.cooldown_until, "
                    "excluded.cooldown_until),last_http_status=excluded.last_http_status",
                    (policy_id, until, status))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def report(self) -> dict:
        """Read only policy-state diagnostics; redact URLs and all credentials."""
        catalog = self.registry.report()
        if not self.state_path.is_file():
            return {**catalog, "state": [], "requests_recorded": 0}
        conn = self._connection()
        try:
            now = self.clock()
            rows = conn.execute(
                "SELECT policy_id,cooldown_until,last_http_status"
                " FROM policy_state ORDER BY policy_id").fetchall()
            state = []
            for policy_id, until, status in rows:
                policy = self.registry.by_id.get(policy_id)
                if policy is None:
                    # Previously classified policies are retained in durable
                    # state, but cannot authorize new outbound requests.
                    count = 0
                else:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM requests "
                        "WHERE policy_id = ? AND requested_at > ?",
                        (policy_id, now - policy.rate["window_seconds"])
                    ).fetchone()[0]
                state.append({
                    "publisher": policy_id,
                    "cooldown_seconds_remaining": max(0, int(until - now)),
                    "last_http_status": status,
                    "requests_in_ledger": count,
                })
            catalog["state"] = state
            catalog["requests_recorded"] = sum(row["requests_in_ledger"]
                                                 for row in state)
            catalog["request_count_scope"] = "active_rolling_windows"
            return catalog
        finally:
            conn.close()
