import json
import unittest
from datetime import datetime, timedelta, timezone

from scout.agent import parse_json_object
from scout.feed import filter_listings, normalize
from scout.rank import rank
from scout.types import Listing, Triaged, Verdict


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


if __name__ == "__main__":
    unittest.main()
