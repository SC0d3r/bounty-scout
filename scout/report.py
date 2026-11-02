"""Markdown and JSON rendering. Every claim in the shortlist is traceable."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from .types import Triaged


def _money(value: Optional[float]) -> str:
    if value is None:
        return "?"
    if value < 1:
        return f"${value:.2f}"
    return f"${value:,.0f}" if value >= 10 else f"${value:.2f}"


def _deadline(item: Triaged) -> str:
    if not item.listing.deadline:
        return "none"
    days = item.listing.days_left
    stamp = item.listing.deadline.strftime("%Y-%m-%d")
    return f"{stamp} ({days:.1f}d)" if days is not None else stamp


def render_markdown(
    *,
    run_id: int,
    feed: str,
    mode: str,
    model: str,
    items: list[Triaged],
    excluded: list[tuple[Any, str]],
    cached: int,
    top_n: int = 10,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Bounty Scout shortlist",
        "",
        f"Generated {now} · run `{run_id}` · mode `{mode}` · model `{model}`",
        f"Feed: <{feed}>",
        "",
        f"**{len(items)} candidates scored, {cached} reused from memory, {len(excluded)} excluded before the model.**",
        "",
        "Scores are deterministic. The model supplies the judgements; it does not choose the order.",
        "",
        "| # | Score | Bounty | Reward | Source | Deadline | Verdict |",
        "|---:|---:|---|---:|---|---|---|",
    ]
    for index, item in enumerate(items[:top_n], start=1):
        verdict = "actionable" if item.verdict.actionable else "not actionable"
        if item.verdict.legitimacy != "unknown":
            verdict += f" · {item.verdict.legitimacy}"
        title = item.listing.title.replace("|", "\\|")[:72]
        lines.append(
            f"| {index} | {item.score:.1f} | [{title}]({item.listing.url}) | "
            f"{_money(item.listing.reward_usd)} | {item.listing.source} | {_deadline(item)} | {verdict} |"
        )

    if items:
        best = items[0]
        actionable = [item for item in items if item.verdict.actionable]
        if not actionable:
            lines += [
                "",
                "## No actionable listing in this scan",
                "",
                "Every candidate is blocked by a hard constraint or a low-confidence model verdict. "
                "The best near-miss is shown below; do not start it without re-checking the page.",
            ]
        lines += [
            "",
            "## Top pick",
            "",
            f"**{best.listing.title}** — {_money(best.listing.reward_usd)} via {best.listing.source}",
            "",
            f"{best.verdict.reason}",
            "",
            f"- Evidence: <{best.listing.url}>",
            f"- Confidence: {best.verdict.confidence:.2f}",
            f"- Requires: {', '.join(best.listing.requires) or 'nothing listed'}",
            f"- Score breakdown: {'; '.join(best.score_reasons)}",
        ]
        if best.verification:
            lines.append(f"- Page check: reachable={best.verification.page_reachable}, still_listed={best.verification.still_listed} — {best.verification.notes}")
        if best.verdict.red_flags:
            lines.append(f"- Red flags: {'; '.join(best.verdict.red_flags)}")

    if excluded:
        lines += ["", "## Excluded before the model", ""]
        for listing, reason in excluded[:20]:
            lines.append(f"- **{listing.title[:80]}** — {reason}")

    lines += [
        "",
        "## Limits",
        "",
        "- A feed entry is not proof of payment. `legit` means the feed fields are coherent, not that the poster has ever paid.",
        "- Verification fetches one page per top listing. It does not sign in, solve challenges, or check a wallet balance.",
        "- Deadline and reward are copied from the feed; re-check both on the listing itself before starting.",
        "",
    ]
    return "\n".join(lines)


def render_json(items: list[Triaged], meta: dict[str, Any]) -> str:
    payload = {
        "meta": meta,
        "shortlist": [
            {
                "rank": index,
                "score": item.score,
                "score_reasons": item.score_reasons,
                "listing": {
                    "ref": item.listing.ref,
                    "source": item.listing.source,
                    "title": item.listing.title,
                    "url": item.listing.url,
                    "reward_usd": item.listing.reward_usd,
                    "currency": item.listing.currency,
                    "network": item.listing.network,
                    "deadline": item.listing.deadline.isoformat() if item.listing.deadline else None,
                    "requires": item.listing.requires,
                },
                "verdict": item.verdict.model_dump(),
                "verification": item.verification.model_dump() if item.verification else None,
            }
            for index, item in enumerate(items, start=1)
        ],
    }
    return json.dumps(payload, indent=2)
