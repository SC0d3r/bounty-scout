"""Deterministic ranking. The model supplies judgements, not the final order.

Keeping the score in ordinary Python makes every placement explainable and
reproducible: the same verdicts always produce the same shortlist.
"""

from __future__ import annotations

import math

from .types import Triaged


def score(item: Triaged) -> Triaged:
    listing = item.listing
    verdict = item.verdict
    points: list[tuple[str, float]] = []

    reward = listing.reward_usd or 0.0
    reward_points = min(25.0, 10.0 * math.log10(1.0 + max(reward, 0.0)))
    points.append((f"reward ${reward:g}", round(reward_points, 1)))

    days = listing.days_left
    if days is None:
        points.append(("no deadline (uncertain)", 3.0))
    elif 2 <= days <= 14:
        points.append((f"{days:.1f} days left", 15.0))
    elif days > 14:
        points.append((f"{days:.1f} days left", 8.0))
    elif days >= 0:
        points.append((f"only {days:.1f} days left", 4.0))
    else:
        points.append(("expired", -40.0))

    if verdict.legitimacy == "legit":
        points.append(("legitimacy: legit", 12.0))
    elif verdict.legitimacy == "suspicious":
        points.append(("legitimacy: suspicious", -30.0))
    else:
        points.append(("legitimacy: unknown", 0.0))

    points.append(("actionable now" if verdict.actionable else "not actionable now", 15.0 if verdict.actionable else -20.0))

    if listing.requires_identity or verdict.requires_kyc:
        points.append(("KYC required", -25.0))
    if listing.requires_payment_upfront or verdict.requires_payment:
        points.append(("upfront payment", -35.0))
    if listing.requires_human_social or verdict.requires_human_social:
        points.append(("human/social gate", -20.0))
    if listing.slots_left and listing.slots_left > 0:
        points.append((f"{listing.slots_left} slots open", 5.0))
    if listing.source == "direct":
        points.append(("direct listing", 5.0))

    total = sum(value for _, value in points)
    item.score = round(max(0.0, min(100.0, total)), 1)
    item.score_reasons = [f"{label} ({value:+.1f})" for label, value in points]
    return item


def rank(items: list[Triaged]) -> list[Triaged]:
    return sorted((score(item) for item in items), key=lambda i: (-i.score, i.listing.title))
