"""Canonical, cross-process publisher policy enforcement for outbound HTTP.

Publisher-specific limits and usage restrictions are *data* in
definitions/source_policies.json. All production HTTPX clients must use
managed_client (or managed_get), not direct HTTPX constructors.

Requests are reserved in a shared SQLite sliding-window ledger before network
I/O. This is process-safe, preserves publisher 429/503 cooldowns, and refuses
unknown origins or use not explicitly permitted. It does not invent a licence,
bypass access controls, assume a VPN can be detected, or alter source archives.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import httpx

POLICY_PATH = Path(__file__).resolve().parents[2] / "definitions" / "source_policies.json"
DEFAULT_LEDGER = Path("/data/source-policy/rate-ledger.sqlite3")
DEFAULT_MAX_WAIT_SECONDS = 3.0
ALLOWED_CLASSES = {
    "publisher_verified", "internal_conservative",
    "restricted_use", "unverified",
}
RIGHTS = {"allowed_with_attribution", "not_cleared", "prohibited"}


class PolicyViolation(ValueError):
    """Access, source-rights, network-origin or catalog rule rejected request."""

    def __init__(self, policy_id: str, reason: str):
        self.policy_id, self.reason = policy_id, reason
        super().__init__(f"source_policy:{policy_id}:{reason}")


class PolicyDeferred(RuntimeError):
    """A bounded request was postponed instead of sleeping through a cooldown."""

    def __init__(self, policy_id: str, reason: str, retry_at: float):
        self.policy_id = policy_id
        self.reason = reason
        self.retry_at = retry_at
        self.retry_after_seconds = max(0, int(retry_at - time.time()) + 1)
        super().__init__(f"source_policy:{policy_id}:{reason}:retry_later")


@dataclass(frozen=True)
class Policy:
    id: str
    hosts: tuple[str, ...]
    classification: str
    evidence_url: str
    rate: dict
    restrictions: dict
    rights: dict


class PolicyRegistry:
    """Versioned publisher classification; reject duplicate/ambiguous host rules."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else POLICY_PATH
        raw = self.path.read_bytes()
        self.sha256 = sha256(raw).hexdigest()
        data = json.loads(raw)
        if (data.get("schema_version") != 1 or data.get("unknown_host") != "deny"
                or not isinstance(data.get("policies"), list)):
            raise PolicyViolation("registry", "invalid_or_permissive_schema")
        self.version = data.get("version")
        self.by_host: dict[str, Policy] = {}
        self.by_id: dict[str, Policy] = {}
        for record in data["policies"]:
            policy = self._parse(record)
            if policy.id in self.by_id:
                raise PolicyViolation("registry", "duplicate_policy_id")
            self.by_id[policy.id] = policy
            for host in policy.hosts:
                if host in self.by_host:
                    raise PolicyViolation("registry", "ambiguous_publisher_hostname")
                self.by_host[host] = policy
        if not self.by_id:
            raise PolicyViolation("registry", "empty_catalog")

    @staticmethod
    def _parse(row: dict) -> Policy:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise PolicyViolation("registry", "malformed_policy")
        rule_id = row["id"]
        hosts = row.get("hosts")
        rate = row.get("rate")
        restrictions = row.get("restrictions")
        rights = row.get("rights")
        if (not isinstance(hosts, list) or not hosts
                or not isinstance(rate, dict)
                or not isinstance(restrictions, dict)
                or not isinstance(rights, dict)):
            raise PolicyViolation(rule_id, "missing_required_policy_fields")
        if (row.get("classification") not in ALLOWED_CLASSES
                or not isinstance(row.get("evidence_url"), str)
                or not row["evidence_url"].startswith("https://")):
            raise PolicyViolation(rule_id, "missing_evidence_or_classification")
        for host in hosts:
            if (not isinstance(host, str) or host != host.lower()
                    or not host or "/" in host or ":" in host or "*" in host
                    or host.startswith(".") or host.endswith(".")):
                raise PolicyViolation(rule_id, "invalid_hostname")
        needed = ("limit", "window_seconds", "min_spacing_seconds",
                  "max_concurrent", "cooldown_429_seconds",
                  "cooldown_503_seconds", "cooldown_access_denied_seconds",
                  "cooldown_other_5xx_seconds", "lease_seconds")
        if any(not isinstance(rate.get(k), (int, float)) for k in needed):
            raise PolicyViolation(rule_id, "invalid_rate_schema")
        if (rate["limit"] < 1 or rate["window_seconds"] < 1
                or rate["max_concurrent"] < 1 or rate["lease_seconds"] < 1
                or any(rate[k] < 0 for k in (
                    "min_spacing_seconds", "cooldown_429_seconds",
                    "cooldown_503_seconds", "cooldown_access_denied_seconds",
                    "cooldown_other_5xx_seconds"))):
            raise PolicyViolation(rule_id, "invalid_rate_bounds")
        if (not isinstance(restrictions.get("methods"), list)
                or not restrictions["methods"]
                or any(m not in {"GET", "HEAD"} for m in restrictions["methods"])
                or not isinstance(restrictions.get("blocked_query_parameters"), list)
                or any(not isinstance(restrictions.get(k), bool) for k in (
                    "require_direct_network_ack", "require_contact_user_agent",
                    "allow_automated_download"))):
            raise PolicyViolation(rule_id, "invalid_restrictions")
        if (rights.get("internal_analysis") not in RIGHTS
                or rights.get("redistribution") not in RIGHTS
                or not isinstance(rights.get("machine_verified_licence"), bool)):
            raise PolicyViolation(rule_id, "invalid_rights")
        return Policy(
            id=rule_id, hosts=tuple(hosts),
            classification=row["classification"], evidence_url=row["evidence_url"],
            rate=rate, restrictions=restrictions, rights=rights)

    def for_url(self, url) -> Policy:
        parts = urlsplit(str(url))
        if (parts.scheme.lower() != "https" or parts.username or parts.password
                or (parts.port is not None and parts.port != 443)):
            raise PolicyViolation("registry", "https_source_required")
        host = (parts.hostname or "").lower().rstrip(".")
        policy = self.by_host.get(host)
        if policy is None:
            raise PolicyViolation("unclassified", "publisher_rule_missing")
        return policy

    def check_request(self, request: httpx.Request, policy: Policy) -> None:
        rules = policy.restrictions
        if request.method.upper() not in rules["methods"]:
            raise PolicyViolation(policy.id, "method_not_permitted")
        if not rules["allow_automated_download"]:
            raise PolicyViolation(policy.id, "automated_download_not_cleared")
        blocked = {key.casefold() for key in rules["blocked_query_parameters"]}
        if any(key.casefold() in blocked
               for key, _ in parse_qsl(request.url.query.decode("utf-8"),
                                       keep_blank_values=True)):
            raise PolicyViolation(policy.id, "prohibited_query_parameter")
        if rules["require_direct_network_ack"] and os.environ.get(
                "FINANCE_OECD_DIRECT_NETWORK_ACK") != "1":
            raise PolicyViolation(policy.id, "direct_network_origin_not_confirmed")
        if rules["require_contact_user_agent"]:
            agent = request.headers.get("user-agent", "")
            if ("@" not in agent and "http://" not in agent
                    and "https://" not in agent):
                raise PolicyViolation(policy.id, "contact_user_agent_required")
        if policy.rights["internal_analysis"] != "allowed_with_attribution":
            raise PolicyViolation(policy.id, "internal_collection_not_cleared")

    def report(self) -> dict:
        return {
            "schema_version": 1,
            "version": self.version,
            "registry_sha256": self.sha256,
            "publisher_count": len(self.by_id),
            "host_count": len(self.by_host),
            "unclassified_hosts_denied": True,
            "publishers": [
                {
                    "id": p.id, "hosts": list(p.hosts),
                    "classification": p.classification,
                    "publisher_evidence": p.evidence_url,
                    "limit": p.rate["limit"],
                    "window_seconds": p.rate["window_seconds"],
                    "min_spacing_seconds": p.rate["min_spacing_seconds"],
                    "max_concurrent": p.rate["max_concurrent"],
                    "require_direct_network_ack":
                        p.restrictions["require_direct_network_ack"],
                    "automated_download_allowed":
                        p.restrictions["allow_automated_download"],
                    "redistribution": p.rights["redistribution"],
                    "licence_machine_verified":
                        p.rights["machine_verified_licence"],
                }
                for p in sorted(self.by_id.values(), key=lambda p: p.id)
            ],
        }


class _ManagedResponseStream(httpx.SyncByteStream):
    """Hold concurrency lease until all source body bytes are consumed/closed."""

    def __init__(self, original: httpx.SyncByteStream, release, heartbeat):
        self.original = original
        self.release_callback = release
        self.heartbeat = heartbeat
        self.closed = False

    def __iter__(self):
        try:
            for chunk in self.original:
                self.heartbeat()
                yield chunk
        finally:
            self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.original.close()
            finally:
                self.release_callback()


class SourcePolicyGate:
    """Atomic cross-process rolling-window reservations and publisher cooldowns.

    Client hooks enforce the rules before sending requests. A response releases
    its concurrency lease and records 429/503 cooldowns (including Retry-After).
    Unreturned requests consume their budget and leave a bounded expiring lease:
    they cannot make the system exceed rate limits after a connection failure.
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

    def _connection(self) -> sqlite3.Connection:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if self.state_path.is_symlink():
            raise PolicyViolation("ledger", "symlink_state_forbidden")
        connection = sqlite3.connect(str(self.state_path), timeout=15,
                                     isolation_level=None)
        connection.execute("PRAGMA busy_timeout=15000")
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
        return connection

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
            next_at, cooldown, _ = conn.execute(
                "SELECT next_at,cooldown_until,last_http_status "
                "FROM policy_state WHERE policy_id = ?", (policy.id,)).fetchone()
            if cooldown > now:
                raise PolicyDeferred(policy.id, "publisher_cooldown", cooldown)
            if next_at > now:
                raise PolicyDeferred(policy.id, "minimum_spacing", next_at)
            rows = conn.execute(
                "SELECT COUNT(*), MIN(requested_at) FROM requests "
                "WHERE policy_id = ? AND requested_at > ?",
                (policy.id, now - rate["window_seconds"])).fetchone()
            if rows[0] >= rate["limit"]:
                raise PolicyDeferred(
                    policy.id, "rolling_window_limit",
                    rows[1] + rate["window_seconds"] + 0.001)
            active = conn.execute(
                "SELECT COUNT(*), MIN(expires_at) FROM leases WHERE policy_id = ?",
                (policy.id,)).fetchone()
            if active[0] >= rate["max_concurrent"]:
                raise PolicyDeferred(policy.id, "concurrency_limit", active[1])
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

    def before_request(self, request: httpx.Request) -> None:
        policy = self.registry.for_url(request.url)
        self.registry.check_request(request, policy)
        lease = self.reserve(policy)
        request.extensions["source_policy_lease"] = (lease, policy.id)

    def after_response(self, response: httpx.Response) -> None:
        entry = response.request.extensions.pop("source_policy_lease", None)
        if entry is None:
            return
        lease, policy_id = entry
        # A publisher block must be persisted before any subsequent request,
        # even if the caller never consumes the error response body.
        if response.status_code in (401, 403, 429) or response.status_code >= 500:
            self.release(lease, policy_id, status=response.status_code,
                         headers=response.headers)
            return
        # HTTPX response hooks run on headers before a streamed body has been
        # consumed. Concurrency applies to the whole download, not just headers.
        last_touch = [self.clock()]
        def heartbeat():
            now = self.clock()
            if now - last_touch[0] >= 30:
                self.keepalive(lease, policy_id)
                last_touch[0] = now
        response.stream = _ManagedResponseStream(
            response.stream, lambda: self.release(lease, policy_id), heartbeat)

    def report(self) -> dict:
        """Read only policy-state diagnostics; redact URLs and all credentials."""
        catalog = self.registry.report()
        if not self.state_path.is_file():
            return {**catalog, "state": [], "requests_recorded": 0}
        conn = self._connection()
        try:
            now = self.clock()
            rows = conn.execute(
                "SELECT p.policy_id,p.cooldown_until,p.last_http_status,"
                "(SELECT COUNT(*) FROM requests r WHERE r.policy_id=p.policy_id)"
                " FROM policy_state p ORDER BY p.policy_id").fetchall()
            catalog["state"] = [{
                "publisher": policy_id,
                "cooldown_seconds_remaining": max(0, int(until - now)),
                "last_http_status": status,
                "requests_in_ledger": count,
            } for policy_id, until, status, count in rows]
            catalog["requests_recorded"] = sum(r[3] for r in rows)
            return catalog
        finally:
            conn.close()


def managed_client(*, policy_gate: SourcePolicyGate | None = None, **kwargs) -> httpx.Client:
    """Single production HTTPX factory; also supports injected test ledgers.

    A direct httpx.Client in runtime code is an architectural violation.
    Redirects, when explicitly allowed by callers, are checked on each hop.
    """
    gate = policy_gate or SourcePolicyGate()
    hooks = kwargs.pop("event_hooks", {})
    hooks = {k: list(v) for k, v in hooks.items()}
    hooks.setdefault("request", []).insert(0, gate.before_request)
    hooks.setdefault("response", []).insert(0, gate.after_response)
    # Environment proxies cannot silently change publisher network origin.
    kwargs.setdefault("trust_env", False)
    return httpx.Client(event_hooks=hooks, **kwargs)


def managed_get(url: str, **kwargs) -> httpx.Response:
    """One-off managed request, for scripts otherwise using httpx.get()."""
    timeout = kwargs.pop("timeout", 30)
    follow_redirects = kwargs.pop("follow_redirects", False)
    with managed_client(timeout=timeout, follow_redirects=follow_redirects) as client:
        return client.get(url, **kwargs)


def policy_summary() -> dict:
    return SourcePolicyGate().report()
