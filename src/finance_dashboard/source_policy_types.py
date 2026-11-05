"""Shared publisher-policy domain contracts and safe failure types."""
from __future__ import annotations
from dataclasses import dataclass
import time

ALLOWED_CLASSES = {"publisher_verified", "internal_conservative", "restricted_use", "unverified"}
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
