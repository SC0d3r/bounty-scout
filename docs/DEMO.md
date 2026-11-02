# Demo video

Target: a 1–5 minute screen recording that shows the agent running and the
result it produces. No human voice or on-camera presence is required by the
Hackathon #5 rules; captions are enough.

The recording is a real terminal session. Long model waits are compressed with
`asciinema rec --idle-time-limit 2`, so the video stays honest while remaining
watchable.

## Preconditions

```bash
cd bounty-scout
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
export OPENMINION_HOME="$PWD/.openminion"
export OPENMINION_DATA_ROOT="$OPENMINION_HOME"
export OPENMINION_CONFIG_PATH="$OPENMINION_HOME/agents.json"
export OTARI_SERVICE_KEY=...          # or any OpenAI-compatible key
export PATH="$PWD/.venv/bin:$PATH"
```

`$OPENMINION_HOME/agents.json` must point `providers.openai` (and
`system.providers.openai`) at the gateway, with `temperature: 0.0` and the agent
profile's `action_policy` set to `{"mode": "bypass"}`.

## Shot list

| Time | Screen | Caption |
|---:|---|---|
| 0:00 | Title card | "Bounty Scout — an OpenMinion agent that turns raw bounty feeds into an evidence-backed shortlist." |
| 0:06 | `openminion --version`, `python -V`, `sqlite3 --version` | "OpenMinion 0.1.17, Python 3.12, SQLite 3.31 — a stock Ubuntu 20.04 box." |
| 0:12 | `bounty-scout selftest` and `head -20 reports/selftest.md` | "First pass is offline and deterministic: hard constraints drop KYC, deposits, social posts and expired rows before any token is spent." |
| 0:30 | `bounty-scout scan --feed fixtures/agent-bounty-feed-2026-11-02.json --limit 6 --verify-top 1 --out reports/demo.md` | "Live pass: 25 real feed rows, 19 excluded, 6 sent to gpt-oss-20b for one triage turn." |
| 0:45 | still scanning | "The model answers go / no / unsure. The score is ordinary Python — the model never chooses the order." |
| 0:55 | `verify:` line appears | "The top candidate is fetched with an SSRF-safe OpenMinion tool; reachability is measured, not guessed." |
| 1:05 | `sed -n '1,40p' reports/demo.md` | "The report keeps the pick, the page evidence, the red flags, and every exclusion." |
| 1:30 | scroll to `Page check` | "7 of 8 title terms and the $125 reward are present on the live page. The model said YES." |
| 1:45 | `bounty-scout runs` | "SQLite memory: verdicts are reused only when the listing fingerprint is unchanged." |
| 1:55 | `openminion skill list` | "The triage workflow ships as an OpenMinion skill, ingested and admitted as verified." |
| 2:05 | `python3 -c ... reports/demo.json` | "The same data is machine-readable for the next agent in the pipeline." |
| 2:15 | End card | "Three OpenMinion bugs found: SQLite < 3.33 migration, config precedence, console-prefixed output_type. Repo: github.com/SC0d3r/bounty-scout" |

## Recording

```bash
# 1. record (compress idle gaps)
asciinema rec /tmp/bounty-scout.cast --idle-time-limit 2 --command "bash /tmp/demo-script.sh"

# 2. render (musl build works on older glibc)
/tmp/agg --font-family "DejaVu Sans Mono" --font-size 18 \
  --theme monokai /tmp/bounty-scout.cast /tmp/bounty-scout.mp4

# 3. burn captions
ffmpeg -i /tmp/bounty-scout.mp4 -vf "subtitles=/tmp/captions.srt:force_style='FontSize=20,Outline=1'" \
  -c:v libx264 -pix_fmt yuv420p docs/demo.mp4
```

Keep `docs/demo.mp4` under ~40 MB. Delete the intermediate `.cast`, PNG frames
and temporary renders afterwards.

## What must not appear on screen

- API keys, `OTARI_SERVICE_KEY`, `agents.json` contents.
- The operator's email, wallet addresses, or any account page.
- Raw model replies that contain the prompt payload beyond the listing fields
  (they are public feed data, but keep the screen clean).

## Honesty rules

- Do not edit the terminal output. Cut idle time, do not fake results.
- If the live run returns "no actionable listing", show that and explain it.
  The finding is part of the project.
- Show the real report file produced by the run that is on screen.
