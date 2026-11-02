"""Data shapes shared by the feed, the agent stages, and the report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class Listing:
    """One normalized bounty from any supported feed."""

    ref: str
    source: str
    title: str
    url: str
    reward_usd: Optional[float]
    currency: str
    network: Optional[str]
    deadline: Optional[datetime]
    requires: list[str] = field(default_factory=list)
    eligibility: str = ""
    slots_left: Optional[int] = None
    first_seen: Optional[str] = None

    @property
    def requires_payment_upfront(self) -> bool:
        return bool({"purchase", "stake", "bond", "deposit"} & set(self.requires))

    @property
    def requires_identity(self) -> bool:
        return "kyc" in {r.lower() for r in self.requires}

    @property
    def requires_human_social(self) -> bool:
        return bool({"x_account", "public_post", "human_only"} & set(self.requires))

    @property
    def days_left(self) -> Optional[float]:
        if not self.deadline:
            return None
        return (self.deadline - utcnow()).total_seconds() / 86400.0

    def prompt_payload(self) -> dict[str, Any]:
        """The smallest faithful representation we send to the model."""

        return {
            "ref": self.ref,
            "source": self.source,
            "title": self.title,
            "reward_usd": self.reward_usd,
            "currency": self.currency,
            "network": self.network,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "requires": self.requires,
            "eligibility": self.eligibility,
            "slots_left": self.slots_left,
            "url": self.url,
        }


class Verdict(BaseModel):
    """A model judgement about one listing. Kept coarse on purpose."""

    ref: str = Field(description="The listing ref, copied verbatim.")
    actionable: bool = Field(
        description="True only if an autonomous agent could start and finish this now."
    )
    legitimacy: str = Field(
        description="One of: legit, suspicious, unknown. Use unknown when the feed has no evidence."
    )
    requires_kyc: bool = False
    requires_payment: bool = False
    requires_human_social: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    red_flags: list[str] = Field(default_factory=list)
    reason: str = Field(description="One or two sentences, citing the feed fields.")


class VerdictBatch(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


class Verification(BaseModel):
    """Second-stage check that the listing page is live and still matches."""

    ref: str
    page_reachable: bool
    still_listed: Optional[bool] = None
    notes: str = ""


@dataclass
class Triaged:
    listing: Listing
    verdict: Verdict
    verification: Optional[Verification] = None
    score: float = 0.0
    score_reasons: list[str] = field(default_factory=list)

    @property
    def evidence_url(self) -> str:
        return self.listing.url
