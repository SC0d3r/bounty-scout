# Demo video

Target: a 1–5 minute screen recording that shows the agent running and the
result it produces.

Published recording: <https://github.com/SC0d3r/bounty-scout/releases/download/demo-v1/demo.mp4>
(1m 12s, H.264 MP4, 1322x1032, video only). It is rendered from the committed
`docs/demo.cast` with `agg`, idle gaps compressed at `--idle-time-limit 8`, and
re-encoded to H.264 with `-pix_fmt yuv420p -movflags +faststart` so it plays in a
browser `<video>` element. No human voice or on-camera presence is required by the
Hackathon #5 rules; captions are enough.

The recording is a real terminal session. Long model waits are compressed, not
cut, so the video stays honest while remaining watchable. `docs/demo.cast` and
`docs/demo-script.sh` are committed so the run can be replayed; the script takes
the model key from the environment and contains no credentials.

## Preconditions

```bash
cd bounty-scout
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
export OPENMINION_HOME="$PWD/.openminion"
export OPENMINION_DATA_ROOT="$OPENMINION_HOME"
export OPENMINION_CONFIG_PATH="$OPENMINION_HOME/agents.json"
export GATEWAY_API_KEY=...           # or any OpenAI-compatible key
export PATH="$PWD/.venv/bin:$PATH"
```

`docs/demo-script.sh` is the exact script used for the recording. It reads the
gateway key from `$GATEWAY_API_KEY` and expects `bounty-scout` on `PATH`.

`$OPENMINION_HOME/agents.json` must point `providers.openai` (and
`system.providers.openai`) at the gateway, with `temperature: 0.0` and the agent
profile's `action_policy` set to `{"mode": "bypass"}`.

## What the 1m 12s cut shows (in order)

The published cut keeps the whole run; only idle waits are compressed. The
scene order is the order of `docs/demo.cast`:

| Scene | Screen | Point |
|---:|---|---|
| 1 | Title card | "Bounty Scout — an OpenMinion 0.1.17 agent that turns raw bounty feeds into an evidence-backed shortlist." |
| 2 | `openminion --version`, `python -V`, `sqlite3.sqlite_version` | OpenMinion 0.1.17, Python 3.12.9, SQLite 3.31.1 on Ubuntu 20.04 (Python installed separately from the 20.04 system 3.8). |
| 3 | `bounty-scout selftest` + `reports/selftest.md` | First pass is offline and deterministic: hard constraints drop KYC, deposits, social posts and expired rows before any token is spent. |
| 4 | `bounty-scout scan --feed fixtures/agent-bounty-feed-2026-11-02.json --limit 6 --verify-top 1` | Live pass on 25 real feed rows; six survive the deterministic filter and go to the model for one triage turn. |
| 5 | the scan finishing | The model answers go / no / unsure; the score and order are ordinary Python. |
| 6 | `reports/demo.md` | The shortlist, the page evidence, the red flags and every exclusion. |
| 7 | "Score breakdown" + the JSON `verification` block | Why the pick ranks where it does; the page check is recorded next to the model verdict. |
| 8 | `bounty-scout runs` | SQLite memory: verdicts are reused only when the listing fingerprint is unchanged. |
| 9 | `openminion skill list` | The triage workflow ships as an OpenMinion skill, ingested and admitted as verified. |
| 10 | End card | Three OpenMinion findings (SQLite < 3.33 migration, config precedence, console-prefixed `output_type`), repo URL, docs/FINDINGS.md. |

A longer 2m15s edit was planned earlier; the published file is the 1m12s cut, so
scenes that were only in that plan (a separate captions track and a second JSON
read) are not in the video. The transcript and commands are in the cast.

## Recording

```bash
# 1. record (compress idle gaps; keep the file inside the repo workspace)
asciinema rec docs/demo.cast --cols 120 --rows 40 --idle-time-limit 8 \
  --command "bash docs/demo-script.sh"

# 2. render (musl build works on older glibc; GNU build needs glibc >= 2.35)
../bin/agg --font-family "DejaVu Sans Mono" --font-size 18 \
  --theme monokai docs/demo.cast demo.mp4

# 3. re-encode for browser playback (GIF-in-MP4 is not a safe delivery codec)
ffmpeg -i demo.mp4 -vf "scale=1322:1032:flags=lanczos" -r 12 \
  -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p \
  -movflags +faststart demo-h264.mp4
```

The published recording is a GitHub release asset (tag `demo-v1`, 1.9 MB), not a
committed binary; `docs/demo.cast` is committed so a judge can replay the run.

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
