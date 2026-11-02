# Cortensor Hackathon #5 submission

**Project:** Bounty Scout — an OpenMinion agent that turns a raw crypto/OSS
bounty feed into an evidence-backed shortlist.

**Repository:** <https://github.com/SC0d3r/bounty-scout> (branch `hackathon-5`;
code snapshot `d776793`, documentation may be newer on the branch)

**Submitted at:** DoraHacks Cortensor Hackathon #5 build
<https://dorahacks.io/build/50881> (hackathon #2418, registration 182467)

**Demo (1m 12s, real run):**
<https://github.com/SC0d3r/bounty-scout/releases/download/demo-v1/demo.mp4>

**Sample output:** [`docs/sample-report.md`](docs/sample-report.md) — the exact
report produced by the run in the video.

---

## Submission checklist

| Requirement | Evidence |
|---|---|
| Public source repository | <https://github.com/SC0d3r/bounty-scout>, Apache-2.0 |
| README with setup and run instructions | [`README.md`](README.md) — install, config, three commands, live feed example |
| Short explanation of the OpenMinion SDK workflow | README §"Pipeline" and §"Design decisions"; two `Agent` sessions (triage, verify), one `@tool` (`fetch_page`), skill `bounty-triage` |
| One working example | `bounty-scout selftest` (offline, deterministic) and `bounty-scout scan --feed ...` (live model + page verification); both in the demo |
| 1–5 minute demo video | Release `demo-v1`, 1m 12s. Real terminal run, idle-time compressed only; no voice required by the rules |
| Building Blocks Tested | README §"Building Blocks Tested"; table below |
| What We Learned | [`docs/FINDINGS.md`](docs/FINDINGS.md); issues [#564](https://github.com/OpenMinion/openminion/issues/564), [#566](https://github.com/OpenMinion/openminion/issues/566), [#567](https://github.com/OpenMinion/openminion/issues/567) |
| Bug-fix bonus | Issue [#564](https://github.com/OpenMinion/openminion/issues/564) + fix PR [#565](https://github.com/OpenMinion/openminion/pull/565): changes addressed on head `701f2ae` (rebased on `dev`, 11/11 migration tests pass on SQLite 3.31.1), awaiting maintainer re-review |

---

## Data and licensing

The code and documentation are Apache-2.0 (`LICENSE`). The demo and test
fixtures are two kinds of input:

- `fixtures/feed.json` is synthetic: hand-written listings that exercise every
  filter branch, with no third-party content.
- `fixtures/agent-bounty-feed-2026-11-02.json` is a snapshot of the public JSON
  feed at `dailydollar-bot/agent-bounty-feed` (25 factual rows: title, URL,
  reward, deadline, source). The feed repository declares no license, so only
  those factual fields are included and no code from it is used. The feed is
  the thing the agent evaluates; it is not bundled as project source.

---

## What it does

1. **Normalize** a JSON feed into typed `Listing` objects.
2. **Filter** deterministically on constraints that must never be delegated to a
   model: KYC, upfront payment/stake/bond, human-only or public-social work,
   expired deadlines, minimum reward.
3. **Triage** the survivors in one model turn. The output contract is one enum
   (`go` / `no` / `unsure`) plus a reason; the reason is audited against the
   input, and a reason that cites a payout or competition count the feed does
   not contain is replaced with a feed-derived one.
4. **Verify** the top candidate with an SSRF-safe `fetch_page` tool call and a
   deterministic title/reward match. Page evidence overrides a model `NO`; the
   disagreement is recorded instead of hidden.
5. **Rank** with ordinary Python. The model never chooses the order.
6. **Report** the shortlist, every exclusion, the score breakdown, and the page
   evidence as Markdown and JSON.

## OpenMinion SDK workflow

- `Agent(...)` is used for two in-process sessions per scan: one triage turn for
  up to six listings, and one verification turn for the top candidate.
- `fetch_page` is an OpenMinion `@tool`; the model calls it during verification.
  If the model's answer is unusable, the deterministic page check still runs.
- `action_policy` must be `{"mode": "bypass"}` for non-interactive tool calls;
  the default `require_confirm` returned a policy prompt as the model's answer.
- SQLite memory keys verdicts by a listing fingerprint, so unchanged listings
  are not re-triaged.
- The `bounty-triage` skill is ingested with `openminion skill ingest` and
  admitted as `verified` with a named check and evidence reference. The
  admission record from the demo data root is committed at
  [`docs/skill-admission.txt`](docs/skill-admission.txt).

## Building Blocks Tested

| Block | Result |
|---|---|
| Agent execution | Works. Two sessions per scan; `Agent.run()` needs no runtime daemon. |
| Models | Works. `deepseek/deepseek-v4-flash` and `openai/gpt-oss-20b` through one OpenAI-compatible gateway; swapping is config, not code. |
| Tools | Works. `fetch_page` called once per verification; bounded, SSRF-checked fetch. |
| Permissions | **Rough edge.** Default `require_confirm` blocks scripted tool calls; `action_policy: {"mode":"bypass"}` is the only working automation path. |
| Sessions | Works. Separate sessions kept triage and verification memory apart. |
| Memory | Works. SQLite store with change fingerprints; cached verdicts reused only when the listing is unchanged. |
| Skills | Works after two steps: `ingest` stages, `admit` requires a verification result and evidence ref. |
| Diagnostics | Adequate. `BOUNTY_SCOUT_DEBUG=1` prints raw model replies; report notes say which evidence supported each verdict. |
| Config | **Rough edge.** `system.providers` silently overrides `providers.*` (#566). |
| Typed output | **Rough edge.** `output_type` fails on the console channel because of the `openminion: ` prefix (#567). |

## What we learned

1. **SQLite floor is undeclared.** Migration v14 uses `UPDATE ... FROM`, which
   needs SQLite ≥ 3.33; a stock Ubuntu 20.04 / Debian 11 Python dies on first
   run. Reported in #564, fix in PR #565 (correlated subquery).
2. **Config precedence is silent.** `config init` writes a `system.providers`
   mirror that wins over `providers.*`; `custom-openai-compatible` is listed but
   rejected at runtime. Reported in #566.
3. **Typed output is unusable on the console channel.** The renderer's
   `openminion: ` prefix breaks `output_type` validation. Reported in #567.
4. **One-enum contracts beat nine-field JSON.** A small open model at
   `temperature=0.2` flipped between all-`no` and all-`go`; at `0.0` with a
   single enum it was stable enough to demo. The deterministic parts must stay
   outside the model.

Full reproductions, expected vs. actual, and suggested fixes are in
[`docs/FINDINGS.md`](docs/FINDINGS.md).

## Reproduce

```bash
git clone https://github.com/SC0d3r/bounty-scout && cd bounty-scout
python3.11 -m venv .venv && . .venv/bin/activate && pip install -e .
python -m unittest discover -s tests          # 15 tests
bounty-scout selftest                         # offline, no model
bounty-scout scan --feed fixtures/agent-bounty-feed-2026-11-02.json \
  --limit 6 --verify-top 1 --out reports/live.md
```

The live scan needs one OpenAI-compatible endpoint (see README). The demo used
`deepseek/deepseek-v4-flash` through Otari, not Cortensor Portal; Portal access
was not available during the build and the rules mark it optional.

## Known limits

- A feed row is not proof of payment. The free feed hides competition and payout
  history; the page check confirms the listing exists, not that it pays.
- The model's judgement is one input; the hard filters and the rank are
  deterministic, and the report shows both.
- The shortlist is a triage aid, not an autonomous claim bot. It never signs,
  pays, or posts anything.
