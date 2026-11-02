"""Feed adapters. The default adapter reads the free Agent Bounty Feed.

The feed is deliberately discovery-only: it says *what* is open, not whether it
is worth doing. Bounty Scout adds the second half.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .types import Listing, parse_iso

DEFAULT_FEED = "https://dailydollar-bot.github.io/agent-bounty-feed/feed.json"
USER_AGENT = "bounty-scout/0.1 (+https://github.com/SC0d3r/bounty-scout)"

# The feed's own vocabulary, kept in sync with its requires_vocabulary block.
KNOWN_REQUIRES = {
    "agent_account",
    "wallet_evm",
    "wallet_solana",
    "github",
    "kyc",
    "purchase",
    "stake",
    "bond",
    "public_post",
    "x_account",
    "human_only",
    "phone",
}


def fetch_feed(url: str = DEFAULT_FEED, timeout: int = 30, max_bytes: int = 4_000_000) -> dict[str, Any]:
    """Fetch a JSON feed without following redirects into the local network."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError(f"feed larger than {max_bytes} bytes")
        return json.loads(raw.decode("utf-8"))


def load_feed(path_or_url: str) -> dict[str, Any]:
    if path_or_url.startswith(("http://", "https://")):
        return fetch_feed(path_or_url)
    return json.loads(Path(path_or_url).read_text(encoding="utf-8"))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _ref(item: dict[str, Any]) -> str:
    for key in ("id", "ref", "referenceCode", "url"):
        value = item.get(key)
        if value:
            return str(value)
    return "sha256:" + hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()[:16]


def normalize(payload: dict[str, Any]) -> list[Listing]:
    """Turn a feed payload into Listing objects, skipping malformed rows."""

    items: Iterable[dict[str, Any]] = payload.get("items") or payload.get("bounties") or []
    listings: list[Listing] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        currency = str(item.get("currency") or "").strip()
        reward = _number(item.get("est_usd"))
        if reward is None and currency.upper() in {"USD", "USDC", "USDT"}:
            reward = _number(item.get("reward"))
        requires = [str(r).strip().lower() for r in (item.get("requires") or []) if str(r).strip()]
        slots = item.get("slots_left")
        listings.append(
            Listing(
                ref=_ref(item),
                source=str(item.get("source") or "unknown"),
                title=title,
                url=url,
                reward_usd=reward,
                currency=currency,
                network=str(item.get("network") or "") or None,
                deadline=parse_iso(item.get("deadline")),
                requires=requires,
                eligibility=str(item.get("eligibility") or ""),
                slots_left=int(slots) if isinstance(slots, (int, float)) else None,
                first_seen=str(item.get("first_seen") or "") or None,
            )
        )
    return listings


def filter_listings(
    listings: Iterable[Listing],
    *,
    min_usd: float = 0.0,
    allow_kyc: bool = False,
    allow_payment: bool = False,
    allow_social: bool = False,
    include_expired: bool = False,
) -> list[Listing]:
    """Apply the operator's hard constraints before any model tokens are spent."""

    kept: list[Listing] = []
    for listing in listings:
        if listing.reward_usd is not None and listing.reward_usd < min_usd:
            continue
        if listing.deadline and listing.days_left is not None and listing.days_left < 0 and not include_expired:
            continue
        if listing.requires_identity and not allow_kyc:
            continue
        if listing.requires_payment_upfront and not allow_payment:
            continue
        if listing.requires_human_social and not allow_social:
            continue
        kept.append(listing)
    return kept
