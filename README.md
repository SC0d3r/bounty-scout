# Bounty Scout

An OpenMinion agent that turns a raw crypto/OSS bounty feed into an
evidence-backed shortlist, so a human or an autonomous agent spends time on the
jobs that can actually be finished and paid.

Built for **Cortensor Hackathon #5**, on **OpenMinion 0.1.17**.

## The problem

Public bounty feeds are discovery layers, not decision layers. A typical row
says *"$125 — RaptorX Research Challenge — requires agent_account,
wallet_solana"*. It does not say that the listing already has 277 submissions,
that the poster has never paid anyone, or that the page is dead. Worse, feeds
routinely mix:

- **dust** ($0.15 questionnaires),
- **lotteries** (winner-take-all contests with hundreds of entries),
- **gates we cannot pass** (KYC, a purchase, a public social post),
- and **real work** that is buried between them.

Bounty Scout applies the operator's hard constraints first, asks a model only
where judgement is needed, and checks the actual listing page before ranking
anything.

## Pipeline

```
feed.json ──► normalize ──► hard filters ──► model triage ──► page verification ──► deterministic rank ──► report
              (typed)       (KYC, money,     (go / no /       (fetch_page tool +      (explainable       (.md + .json)
                             social, deadline) unsure)          title/reward match)     score)
```

1. **Normalize** the feed into `Listing` objects. Malformed rows are skipped,
   never guessed.
2. **Filter** on the constraints that must never be delegated to a model:
   KYC, an upfront purchase/stake/bond, a human or public-social requirement,
   expired deadlines, and a minimum reward.
3. **Triage** the survivors in one model turn. The model's entire output
   contract is `ref`, `decision` (`go` / `no` / `unsure`), `reason`, and
   `red_flags`. Missing fields are coerced conservatively instead of throwing
   the batch away.
4. **Verify** the top candidate: an OpenMinion `@tool` fetches the public page,
   the model answers YES/NO/UNSURE, and a deterministic check counts title-term
   overlap and looks for the reward amount. Reachability is measured, not
   guessed.
5. **Rank** with a fixed formula in `scout/rank.py`: reward, deadline,
   legitimacy, actionability, KYC/payment/social penalties, open slots. The
   model never chooses the order.
6. **Remember** verdicts in SQLite, keyed by a fingerprint of the listing, so a
   re-scan reuses judgements only when the listing has not changed.

## Quick start

Requirements: Python 3.11+, an OpenMinion install, and an OpenAI-compatible
model endpoint. The demo uses `deepseek/deepseek-v4-flash` through an
OpenAI-compatible gateway; `openai/gpt-oss-20b` also works, with the caveats in
`docs/FINDINGS.md`.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Configure OpenMinion once. This walkthrough uses an OpenAI-compatible gateway;
any provider from `openminion setup --list-providers` works.

```bash
export OPENMINION_HOME="$PWD/.openminion"
export OPENMINION_DATA_ROOT="$OPENMINION_HOME"
openminion config init --provider openai
```

Then edit `$OPENMINION_HOME/agents.json` and set **both** provider blocks (see
`docs/FINDINGS.md` for why both):

```json
{
  "providers": {
    "openai": {
      "base_url": "https://your-gateway.example/v1",
      "api_key_env": "GATEWAY_API_KEY",
      "model": "deepseek/deepseek-v4-flash",
      "temperature": 0.0
    }
  },
  "system": {
    "providers": {
      "openai": {
        "base_url": "https://your-gateway.example/v1",
        "api_key_env": "GATEWAY_API_KEY",
        "model": "deepseek/deepseek-v4-flash",
        "temperature": 0.0
      }
    }
  }
}
```

Also set `"action_policy": {"mode": "bypass"}` on the agent profile if you run
non-interactively; the default policy asks for confirmation before tool calls.

```bash
export GATEWAY_API_KEY=...
export OPENMINION_CONFIG_PATH="$OPENMINION_HOME/agents.json"

# offline: no model calls, uses the feed's own `requires` list
bounty-scout selftest

# live: triage + page verification
bounty-scout scan --feed fixtures/agent-bounty-feed-2026-11-02.json \
  --limit 6 --verify-top 1 --out reports/live-feed.md
```

`scan` also accepts a live URL:

```bash
bounty-scout scan --feed https://dailydollar-bot.github.io/agent-bounty-feed/feed.json
```

## Commands

| Command | What it does |
|---|---|
| `bounty-scout selftest` | Offline run on the bundled fixture; no model, no network. |
| `bounty-scout scan --feed F --limit N --verify-top K` | Full pipeline. `--allow-kyc`, `--allow-payment`, `--allow-social` relax the hard filters. |
| `bounty-scout runs` | Recent runs from SQLite: mode, counts, cache hits. |

Useful environment variables:

- `BOUNTY_SCOUT_DB` — SQLite path (default `data/scout.db`)
- `BOUNTY_SCOUT_DEBUG=1` — print raw model replies to stderr
- `OPENMINION_CONFIG_PATH` — OpenMinion `agents.json`

## What the report contains

Every shortlist row carries its score and the exact points that produced it:

```
| # | Score | Bounty | Reward | Source | Deadline | Verdict |
| 1 | 16.0  | RaptorX Research Challenge … | $125 | superteam | 2026-11-08 (5.5d) | not actionable |
```

The top pick section adds:

- the model's reason (or a reason derived from feed fields when the model omits one),
- the evidence URL,
- the page check (`reachable`, `still_listed`, title-term overlap, reward match),
- red flags,
- and the full score breakdown.

The same data is written as JSON for downstream tools.

## Design decisions

**Deterministic constraints, model judgement.** Whether a listing requires KYC
is a fact in the feed, not an opinion. Whether a task is realistically
finishable by an autonomous agent *today* is a judgement. The split keeps the
model's job small and the output auditable.

**One enum instead of nine booleans.** The first version asked for a nine-field
JSON verdict. `gpt-oss-20b` repeatedly dropped keys, and a single dropped key
invalidated the whole batch. Reducing the contract to `go`/`no`/`unsure` plus a
reason, and deriving the risk flags deterministically, made the pipeline
usable. This is documented as a finding, not hidden.

**The model never ranks.** `scout/rank.py` is ordinary Python. The same
verdicts always produce the same order, and every score can be explained.

**The feed is untrusted.** The verifier's `fetch_page` tool only accepts public
HTTP(S), resolves and rejects private/loopback/link-local addresses, disables
proxies and redirects into the local network, caps the body at 120 KB, strips
scripts/styles, and returns at most 3,000 characters of visible text.

**Cache only on change.** A verdict is reused only if the listing's title,
reward, requirements, deadline and URL are unchanged and the verdict is younger
than seven days. Offline and live verdicts are stored separately.

## Building Blocks Tested

From the Hackathon #5 list, this project exercises:

- **Agent execution** — `Agent(...)` in-process sessions for triage and
  verification.
- **Models** — hosted `deepseek-v4-flash` and `gpt-oss-20b` through the same
  OpenAI-compatible gateway, with `temperature=0` for stable verdicts. Swapping
  the model is a config change, not a code change.
- **Tools** — `fetch_page` as an OpenMinion `@tool`, called by the model during
  verification, with a deterministic fallback when the model's answer is
  unusable.
- **Permissions** — `action_policy` had to be set to `bypass` for a
  non-interactive tool call; the default policy blocked the first live
  verification run.
- **Sessions** — a session per scan and a separate session for verification.
- **Memory** — SQLite run/listing/verdict memory with change fingerprints.
- **Skills** — `skills/bounty-triage/SKILL.md`, ingested with
  `openminion skill ingest` and admitted as `verified` with an explicit
  verification check and evidence reference.
- **Diagnostics** — `BOUNTY_SCOUT_DEBUG=1` records raw model replies; the report
  records exactly which evidence supported each verdict.

Three OpenMinion bugs found while building this are written up with minimal
reproductions in [`docs/FINDINGS.md`](docs/FINDINGS.md):

1. Migration v14 fails on SQLite < 3.33 (`UPDATE ... FROM`), which blocks the
   first run on Ubuntu 20.04.
2. `config init` writes a `system.providers` mirror that silently overrides the
   top-level `providers` block.
3. `Agent.run()` returns console-rendered text (`openminion: …`), so
   `output_type` validation always fails.

## Limits (read before trusting a shortlist)

- **A feed entry is not proof of payment.** `legit` means the feed fields are
  coherent, not that the poster has ever paid.
- **The free feed hides competition.** Submission counts, payout track records
  and verification evidence are behind the feed's paid trust layer. A cheap
  lottery can look like a clean job until you open the page.
- **Verification checks one page.** It does not sign in, solve a captcha, or
  check a wallet balance.
- **Reward and deadline are copied from the feed.** Re-check both on the listing
  before starting work.
- **No transaction is ever signed.** The scout reads public pages and writes
  local files. It has no wallet keys.

## Repository layout

```
scout/
  types.py     data shapes, feed normalization helpers
  feed.py      feed fetch/normalize/filter
  store.py     SQLite runs, listings, verdict cache
  agent.py     OpenMinion prompts, triage, verification, JSON repair
  tools.py     SSRF-safe fetch_page tool
  rank.py      deterministic score
  report.py    Markdown + JSON rendering
  cli.py       scan / runs / selftest
fixtures/      frozen real feed snapshot + small test fixture
tests/         8 offline unit tests
skills/        bounty-triage SKILL.md for OpenMinion
docs/          DEMO.md, FINDINGS.md
```

## License

Apache-2.0. See `LICENSE`.
