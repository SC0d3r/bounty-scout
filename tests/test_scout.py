import json
import unittest
from datetime import datetime, timedelta, timezone

from scout.agent import _evidence, _reason_cites_unverified_count, parse_json_object
from scout.cli import _apply_verification
from scout.feed import filter_listings, normalize
from scout.rank import rank
from scout.types import Listing, Triaged, Verdict, Verification


def listing(**overrides):
    base = dict(
        ref="ref-1",
        source="direct",
        title="Write a short guide",
        url="https://example.com/bounty",
        reward_usd=10.0,
        currency="USDC",
        network="base",
        deadline=datetime.now(timezone.utc) + timedelta(days=5),
        requires=["agent_account"],
    )
    base.update(overrides)
    return Listing(**base)


class FeedTests(unittest.TestCase):
    def test_normalize_uses_est_usd(self):
        payload = {
            "items": [
                {
                    "id": "x:1",
                    "source": "x",
                    "title": "A task",
                    "url": "https://example.com/a",
                    "reward": 5,
                    "currency": "USD",
                    "est_usd": 4.5,
                    "requires": ["Agent_Account"],
                    "deadline": "2026-12-01T00:00:00Z",
                }
            ]
        }
        items = normalize(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].reward_usd, 4.5)
        self.assertEqual(items[0].requires, ["agent_account"])
        self.assertIsNotNone(items[0].deadline)

    def test_filter_drops_hard_constraints(self):
        items = [
            listing(ref="ok"),
            listing(ref="kyc", requires=["kyc"]),
            listing(ref="pay", requires=["purchase"]),
            listing(ref="social", requires=["x_account"]),
            listing(ref="old", deadline=datetime.now(timezone.utc) - timedelta(days=1)),
        ]
        kept = filter_listings(items)
        self.assertEqual([item.ref for item in kept], ["ok"])

    def test_filter_respects_min_usd(self):
        kept = filter_listings([listing(ref="cheap", reward_usd=0.2)], min_usd=1)
        self.assertEqual(kept, [])


class RankTests(unittest.TestCase):
    def item(self, **verdict):
        data = dict(
            ref="r",
            actionable=True,
            legitimacy="legit",
            requires_kyc=False,
            requires_payment=False,
            requires_human_social=False,
            confidence=0.8,
            red_flags=[],
            reason="test",
        )
        data.update(verdict)
        return Triaged(listing(), Verdict(**data))

    def test_actionable_beats_suspicious(self):
        good = self.item()
        bad = self.item(legitimacy="suspicious")
        ordered = rank([bad, good])
        self.assertIs(ordered[0], good)
        self.assertGreater(good.score, bad.score)

    def test_kyc_is_penalised(self):
        clean = self.item()
        kyc = self.item(requires_kyc=True)
        rank([clean, kyc])
        self.assertGreater(clean.score, kyc.score)


class ParseTests(unittest.TestCase):
    def test_console_prefix(self):
        self.assertEqual(parse_json_object('openminion: {"verdicts": []}'), {"verdicts": []})

    def test_fenced_json(self):
        text = '```json\n{"verdicts": [{"ref": "a"}]}\n```'
        self.assertEqual(parse_json_object(text)["verdicts"][0]["ref"], "a")

    def test_plain_json(self):
        self.assertEqual(parse_json_object('{"ok": true}'), {"ok": True})


class EvidenceAuditTests(unittest.TestCase):
    def test_claim_audit_rejects_invented_counts(self):
        for reason in (
            "the poster paid 20 and rejected 5",
            "only 3 winners from 100 entries",
            "277 submissions, 0 accepted",
            "4 applicants",
        ):
            self.assertTrue(_reason_cites_unverified_count(reason), reason)

    def test_claim_audit_keeps_feed_derived_reasons(self):
        for reason in (
            "feed: $3, no deadline, requires agent_account, wallet_evm; model: go",
            "openminion: model decision go",
            "deadline is in 5 days and the reward is $125",
        ):
            self.assertFalse(_reason_cites_unverified_count(reason), reason)

    def test_evidence_accepts_matching_page(self):
        item = listing(title="Write a short guide about bounty triage", reward_usd=10.0)
        reachable, ok, note = _evidence(
            item, "Bounty: write a short guide about bounty triage. Reward $10."
        )
        self.assertTrue(reachable)
        self.assertTrue(ok)
        self.assertIn("found", note)

    def test_evidence_rejects_unrelated_page(self):
        item = listing(title="Write a short guide about bounty triage", reward_usd=10.0)
        reachable, ok, _ = _evidence(item, "A completely different product page")
        self.assertTrue(reachable)
        self.assertFalse(ok)

    def test_evidence_reports_fetch_failure(self):
        item = listing()
        reachable, ok, note = _evidence(item, "ERROR timeout")
        self.assertFalse(reachable)
        self.assertFalse(ok)
        self.assertIn("fetch failed", note)

    def test_verification_marks_dead_page_suspicious(self):
        verdict = Verdict(ref="ref-1", actionable=True, legitimacy="unknown", reason="test")
        _apply_verification(
            verdict, Verification(ref="ref-1", page_reachable=False, still_listed=False)
        )
        self.assertFalse(verdict.actionable)
        self.assertEqual(verdict.legitimacy, "suspicious")
        self.assertIn("listing page is unreachable", verdict.red_flags)

    def test_verification_keeps_live_page_verdict(self):
        verdict = Verdict(ref="ref-1", actionable=True, legitimacy="unknown", reason="test")
        _apply_verification(
            verdict, Verification(ref="ref-1", page_reachable=True, still_listed=True)
        )
        self.assertTrue(verdict.actionable)
        self.assertEqual(verdict.legitimacy, "unknown")
        self.assertEqual(verdict.red_flags, [])


if __name__ == "__main__":
    unittest.main()
