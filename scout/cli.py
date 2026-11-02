"""Command line entry point: scan a feed, rank it, write a shortlist."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .agent import (
    MODEL_LABEL,
    build_agent,
    offline_verdict,
    triage,
)
from .feed import DEFAULT_FEED, filter_listings, load_feed, normalize
from .rank import rank
from .report import render_json, render_markdown
from .store import Store
from .types import Listing, Triaged, Verdict, Verification


def _exclusion_reason(listing: Listing, *, allow_kyc: bool, allow_payment: bool, allow_social: bool) -> str | None:
    if listing.requires_identity and not allow_kyc:
        return "requires KYC"
    if listing.requires_payment_upfront and not allow_payment:
        return "requires an upfront payment, stake, or bond"
    if listing.requires_human_social and not allow_social:
        return "requires a human, phone, or public social post"
    if listing.deadline and (listing.days_left or 0) < 0:
        return "deadline has passed"
    return None


def _apply_verification(verdict: Verdict, check: Verification) -> Verdict:
    if not check.page_reachable:
        verdict.actionable = False
        verdict.legitimacy = "suspicious"
        verdict.red_flags = [*verdict.red_flags, "listing page is unreachable"]
    elif check.still_listed is False:
        verdict.actionable = False
        verdict.legitimacy = "suspicious"
        verdict.red_flags = [*verdict.red_flags, "page no longer shows the bounty"]
    return verdict


def command_scan(args: argparse.Namespace) -> int:
    store = Store(args.db)
    payload = load_feed(args.feed)
    all_listings = normalize(payload)
    store.upsert_listings(all_listings)

    filtered: list[Listing] = []
    excluded: list[tuple[Listing, str]] = []
    for listing in all_listings:
        reason = _exclusion_reason(
            listing,
            allow_kyc=args.allow_kyc,
            allow_payment=args.allow_payment,
            allow_social=args.allow_social,
        )
        if reason:
            excluded.append((listing, reason))
            continue
        if listing.reward_usd is not None and listing.reward_usd < args.min_usd:
            excluded.append((listing, f"reward below --min-usd {args.min_usd:g}"))
            continue
        filtered.append(listing)

    filtered.sort(key=lambda item: (-(item.reward_usd or 0.0), item.title))
    candidates = filtered[: args.limit]
    for extra in filtered[args.limit :]:
        excluded.append((extra, f"outside the top {args.limit} by reward"))

    mode = "offline" if args.offline else "live"
    model = "heuristic" if args.offline else args.model_label
    print(
        f"filter: {len(all_listings)} seen, {len(candidates)} kept, {len(excluded)} excluded",
        file=sys.stderr,
    )
    run_id = store.start_run(args.feed, mode, model)

    verdicts: dict[str, Verdict] = {}
    checks: dict[str, Verification] = {}
    cached = 0
    if args.offline:
        for listing in candidates:
            verdicts[listing.ref] = offline_verdict(listing)
    else:
        pending: list[Listing] = []
        for listing in candidates:
            remembered = store.cached_verdict(listing, mode="live")
            if remembered is not None:
                verdicts[listing.ref] = remembered
                cached += 1
            else:
                pending.append(listing)

        if pending:
            print(f"triage: model pass on {len(pending)} listing(s), {cached} from memory", file=sys.stderr)
            agent = build_agent(config_path=args.config, session_id=f"scout-{run_id}")
            try:
                for verdict in triage(agent, pending):
                    verdicts[verdict.ref] = verdict
                print(f"triage: {len(pending)} verdict(s) received", file=sys.stderr)
            except Exception as exc:  # keep the shortlist usable when the model fails
                print(f"warning: model triage failed ({type(exc).__name__}: {exc}); using heuristics", file=sys.stderr)
                for listing in pending:
                    verdicts.setdefault(listing.ref, offline_verdict(listing))
        # any listing the model skipped still gets a conservative verdict
        for listing in candidates:
            verdicts.setdefault(listing.ref, offline_verdict(listing))

        if args.verify_top > 0:
            verifier = build_verifier(args.config, f"scout-{run_id}-verify")
            ordered = rank([Triaged(listing, verdicts[listing.ref]) for listing in candidates])
            checks: dict[str, Verification] = {}
            for item in ordered[: args.verify_top]:
                if not item.verdict.actionable and item.verdict.confidence >= 0.6:
                    continue
                try:
                    check = verifier(item.listing)
                except Exception as exc:
                    print(f"warning: verification failed for {item.listing.ref} ({type(exc).__name__})", file=sys.stderr)
                    continue
                checks[item.listing.ref] = check
                verdicts[item.listing.ref] = _apply_verification(item.verdict, check)
                print(
                    f"verify: {item.listing.title[:48]} -> reachable={check.page_reachable} "
                    f"still_listed={check.still_listed}",
                    file=sys.stderr,
                )

    for listing in candidates:
        store.save_verdict(run_id, listing, verdicts[listing.ref], mode=mode)

    items = rank(
        [
            Triaged(listing, verdicts[listing.ref], verification=checks.get(listing.ref) if not args.offline else None)
            for listing in candidates
        ]
    )
    store.finish_run(run_id, seen=len(all_listings), kept=len(candidates), cached=cached)

    out_path = Path(args.out) if args.out else Path("reports") / f"scan-{run_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_markdown(
            run_id=run_id,
            feed=args.feed,
            mode=mode,
            model=model,
            items=items,
            excluded=excluded,
            cached=cached,
        ),
        encoding="utf-8",
    )
    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            render_json(
                items,
                {
                    "run_id": run_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "feed": args.feed,
                    "mode": mode,
                    "model": model,
                    "seen": len(all_listings),
                    "kept": len(candidates),
                    "cached": cached,
                },
            ),
            encoding="utf-8",
        )

    print(f"run {run_id}: {len(all_listings)} seen, {len(candidates)} kept, {cached} cached, {len(excluded)} excluded")
    for index, item in enumerate(items[:5], start=1):
        print(f"  {index}. [{item.score:5.1f}] {item.listing.title[:64]} (${item.listing.reward_usd or 0:g})")
    print(f"report: {out_path}")
    store.close()
    return 0


def build_verifier(config_path: str | None, session_id: str):
    from openminion import Agent

    from .agent import VERIFY_INSTRUCTIONS
    from .tools import fetch_page

    def _run(listing: Listing) -> Verification:
        with Agent(
            instructions=VERIFY_INSTRUCTIONS,
            tools=[fetch_page],
            config_path=config_path,
            session_id=session_id,
            name="bounty-scout-verifier",
        ) as agent:
            from .agent import verify

            return verify(agent, listing)

    return _run


def command_runs(args: argparse.Namespace) -> int:
    store = Store(args.db)
    for row in store.recent_runs(args.limit):
        print(
            f"{row['id']:>4} {row['started_at']} {row['mode']:<7} "
            f"seen={row['listings_seen']} kept={row['listings_kept']} cached={row['verdicts_cached']}"
        )
    store.close()
    return 0


def command_selftest(args: argparse.Namespace) -> int:
    args.offline = True
    args.feed = args.fixture
    args.min_usd = 0.0
    args.limit = 50
    args.verify_top = 0
    args.out = "reports/selftest.md"
    args.json_out = "reports/selftest.json"
    args.allow_kyc = False
    args.allow_payment = False
    args.allow_social = False
    args.model_label = "heuristic"
    return command_scan(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bounty-scout", description="Evidence-backed bounty triage on OpenMinion.")
    parser.add_argument("--db", default=os.environ.get("BOUNTY_SCOUT_DB", "data/scout.db"))
    parser.add_argument("--config", default=os.environ.get("OPENMINION_CONFIG_PATH"))
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan a feed and write a shortlist")
    scan.add_argument("--feed", default=DEFAULT_FEED)
    scan.add_argument("--min-usd", type=float, default=0.0)
    scan.add_argument("--limit", type=int, default=20)
    scan.add_argument("--out", default="")
    scan.add_argument("--json-out", default="")
    scan.add_argument("--offline", action="store_true", help="no model calls; use the feed's own constraints")
    scan.add_argument("--verify-top", type=int, default=1, help="fetch and check the top N pages in live mode")
    scan.add_argument("--allow-kyc", action="store_true")
    scan.add_argument("--allow-payment", action="store_true")
    scan.add_argument("--allow-social", action="store_true")
    scan.add_argument("--model-label", default=os.environ.get("BOUNTY_SCOUT_MODEL_LABEL", MODEL_LABEL))
    scan.set_defaults(func=command_scan)

    runs = sub.add_parser("runs", help="show recent runs")
    runs.add_argument("--limit", type=int, default=10)
    runs.set_defaults(func=command_runs)

    selftest = sub.add_parser("selftest", help="offline run on the bundled fixture")
    selftest.add_argument("--fixture", default="fixtures/feed.json")
    selftest.set_defaults(func=command_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
