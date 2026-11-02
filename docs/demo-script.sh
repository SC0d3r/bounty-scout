#!/bin/bash
# The exact terminal session recorded in docs/demo.cast.
# Requires: bounty-scout + openminion on PATH, a configured agents.json, and
# $GATEWAY_API_KEY in the environment. No credentials are stored here.
set -u
cd "$(dirname "$0")/.." || exit 1

: "${OPENMINION_HOME:=${OPENMINION_HOME:-$PWD/.openminion}}"
: "${OPENMINION_DATA_ROOT:=$OPENMINION_HOME}"
: "${OPENMINION_CONFIG_PATH:=$OPENMINION_HOME/agents.json}"
: "${GATEWAY_API_KEY:?set GATEWAY_API_KEY to your OpenAI-compatible key}"
export OPENMINION_HOME OPENMINION_DATA_ROOT OPENMINION_CONFIG_PATH GATEWAY_API_KEY
export BOUNTY_SCOUT_MODEL_LABEL="${BOUNTY_SCOUT_MODEL_LABEL:-openai/gpt-oss-20b}"

rm -f data/demo.db reports/demo.md reports/demo.json
clear
printf '\033[1;36mBounty Scout\033[0m  ·  an OpenMinion 0.1.17 agent for evidence-backed bounty triage\n'
printf 'Cortensor Hackathon #5  ·  github.com/SC0d3r/bounty-scout\n\n'
sleep 2

printf '\033[1;33m── 1. environment ─────────────────────────────────────\033[0m\n'
printf '$ openminion --version\n'; openminion --version
printf '$ python -V\n'; python -V
printf '$ python -c "import sqlite3; print(sqlite3.sqlite_version)"\n'; python -c "import sqlite3; print(sqlite3.sqlite_version)"
sleep 2

printf '\n\033[1;33m── 2. deterministic pass (no model, no network) ───────\033[0m\n'
printf '$ bounty-scout --db data/demo.db selftest\n'
bounty-scout --db data/demo.db selftest
printf '\n$ sed -n "1,20p" reports/selftest.md\n'
sed -n '1,20p' reports/selftest.md
sleep 3

printf '\n\033[1;33m── 3. live pass: real feed, model triage, page check ──\033[0m\n'
printf '$ bounty-scout --db data/demo.db scan --feed fixtures/agent-bounty-feed-2026-11-02.json \\\n'
printf '    --limit 6 --verify-top 1 --out reports/demo.md --json-out reports/demo.json\n'
time bounty-scout --db data/demo.db scan --feed fixtures/agent-bounty-feed-2026-11-02.json --limit 6 --verify-top 1 --out reports/demo.md --json-out reports/demo.json
sleep 2

printf '\n\033[1;33m── 4. the report ───────────────────────────────────────\033[0m\n'
printf '$ sed -n "1,38p" reports/demo.md\n'
sed -n '1,38p' reports/demo.md
sleep 3

printf '\n\033[1;33m── 5. why it ranks where it ranks ──────────────────────\033[0m\n'
printf '$ grep -A4 "Score breakdown" reports/demo.md\n'
grep -A4 'Score breakdown' reports/demo.md | head -10
printf '\n$ python -c "import json; ... verification"\n'
python3 -c "import json;d=json.load(open('reports/demo.json'));print(json.dumps(d['shortlist'][0]['verification'], indent=1))"
sleep 3

printf '\n\033[1;33m── 6. memory and skills ────────────────────────────────\033[0m\n'
printf '$ bounty-scout --db data/demo.db runs\n'
bounty-scout --db data/demo.db runs
printf '\n$ openminion skill list\n'
openminion skill list
sleep 3

printf '\n\033[1;33m── what it found ───────────────────────────────────────\033[0m\n'
printf '3 reproducible OpenMinion findings: migration v14 on SQLite < 3.33,\n'
printf 'system.providers overriding providers.openai, and console-prefixed\n'
printf 'output_type validation. Details: docs/FINDINGS.md\n\n'
printf 'Code: github.com/SC0d3r/bounty-scout (branch hackathon-5)\n'
sleep 4
