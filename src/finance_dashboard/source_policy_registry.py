"""Versioned canonical publisher rules, licence restrictions and host mapping."""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
import httpx
from .source_policy_types import Policy, PolicyViolation, ALLOWED_CLASSES, RIGHTS

POLICY_PATH = Path(__file__).resolve().parents[2] / "definitions" / "source_policies.json"

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
        acknowledgements = {
            value.strip() for value in os.environ.get(
                "FINANCE_SOURCE_POLICY_ACKNOWLEDGED", "").split(",")
            if value.strip()
        }
        if rules["require_direct_network_ack"] and policy.id not in acknowledgements:
            raise PolicyViolation(policy.id, "direct_network_origin_not_confirmed")
        if rules["require_contact_user_agent"]:
            agent = request.headers.get("user-agent", "")
            if ("@" not in agent and "http://" not in agent
                    and "https://" not in agent):
                raise PolicyViolation(policy.id, "contact_user_agent_required")
        if policy.rights["internal_analysis"] != "allowed_with_attribution":
            raise PolicyViolation(policy.id, "internal_collection_not_cleared")

    def require_redistribution_clearance(self, url: str) -> dict:
        """Fail closed for publication/export using a publisher's source data.

        Transport access does not confer external redistribution rights.
        Only explicit, independently confirmed canonical rights may unlock it.
        """
        policy = self.for_url(url)
        if (not policy.rights["machine_verified_licence"]
                or policy.rights["redistribution"] != "allowed_with_attribution"):
            raise PolicyViolation(policy.id, "redistribution_not_cleared")
        return {
            "publisher": policy.id, "required_attribution": True,
            "rights_verified": True,
        }

    def report(self) -> dict:
        acknowledged = {
            value.strip() for value in os.environ.get(
                "FINANCE_SOURCE_POLICY_ACKNOWLEDGED", "").split(",")
            if value.strip()
        }
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
                    "operator_acknowledged": p.id in acknowledged,
                    "automated_download_allowed":
                        p.restrictions["allow_automated_download"],
                    "redistribution": p.rights["redistribution"],
                    "licence_machine_verified":
                        p.rights["machine_verified_licence"],
                }
                for p in sorted(self.by_id.values(), key=lambda p: p.id)
            ],
        }
