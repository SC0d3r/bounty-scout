# OpenMinion 0.1.17 findings

Three issues found while building Bounty Scout on Ubuntu 20.04 (Python 3.12.9,
SQLite 3.31.1). Each one is reproducible from a clean install, each one cost
real time, and each one has a small fix or workaround.

Environment:

```
openminion 0.1.17 (PyPI)
python 3.12.9
sqlite3 3.31.1
Ubuntu 20.04
```

---

## 1. Migration v14 fails on SQLite < 3.33, blocking the first run

**Severity:** blocker. A fresh install cannot start on Ubuntu 20.04, Debian 11,
or any system Python linked against SQLite 3.31.

**Reproduce:**

```bash
python3.12 -m venv .venv
.venv/bin/pip install openminion==0.1.17
export OPENMINION_HOME="$PWD"
export OPENMINION_DATA_ROOT="$OPENMINION_HOME/.openminion"
.venv/bin/openminion config init --provider echo
.venv/bin/openminion run --no-progress "hello"
```

**Observed:**

```
openminion: Migration v14 (add_room_participant_join_seq) failed: near "FROM": syntax error
```

**Cause:** `openminion/modules/storage/runtime/migrations.py`, migration 14:

```sql
UPDATE room_participants
SET join_seq = numbered.join_seq
FROM (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY session_id
            ORDER BY joined_at ASC, id ASC
        ) AS join_seq
    FROM room_participants
) AS numbered
WHERE room_participants.id = numbered.id
```

`UPDATE ... FROM` requires SQLite 3.33 (2020-08-14). Python 3.8/3.9 on Ubuntu
20.04 ships 3.31.1, and OpenMinion advertises Python >= 3.11, so this is not an
exotic configuration. A source comment next to the migration acknowledges that
the statement "needs SQLite 3.33", but the package metadata does not declare a
SQLite floor and the failure is a hard stop on first run rather than a warning.

**Fix that works on the old SQLite** (correlated subquery, same result):

```sql
UPDATE room_participants
SET join_seq = (
    SELECT COUNT(*) + 1
    FROM room_participants AS earlier
    WHERE earlier.session_id = room_participants.session_id
      AND (
          earlier.joined_at < room_participants.joined_at
          OR (
              earlier.joined_at = room_participants.joined_at
              AND earlier.id < room_participants.id
          )
      )
)
```

This is the patch used to run Bounty Scout locally. It preserves the
`ORDER BY joined_at ASC, id ASC` semantics of the original window function.

**Suggested upstream options:** use the correlated subquery above, or require
SQLite >= 3.33 explicitly and document it, or catch the error and fall back.

---

## 2. `config init` writes a `system.providers` mirror that silently wins

**Severity:** high. A documented-looking edit has no effect and there is no
warning.

**Reproduce:**

1. `openminion config init --provider openai`
2. Edit only `providers.openai` in `agents.json`: set `base_url`,
   `api_key_env`, `model`.
3. Run `openminion config show` — the edit is absent.
4. Run a turn — the provider still points at `https://api.openai.com/v1` and
   reports `incorrect API key`.

**Observed:** `config show` prints the default `api.openai.com` block even
though the file on disk contains the edited one.

**Cause:** `base/config/parser/payload.py` merges the top-level `providers`
block with `system.providers`, and the system mirror wins:

```python
effective_providers_payload = _merge_mapping_dicts(
    mapping_payload(payload, "providers"),
    system_providers_payload,
)
```

`config init` writes a full copy of every provider into `system.providers`, so
the mirror is never empty and always overrides the top-level block.

**Workaround:** edit both blocks, or delete `system.providers` before editing
the top-level one.

**Suggested fix:** either stop writing the mirror, or merge in the other order
(explicit top-level wins), or warn when both blocks define the same provider
with different values. A `config show --source` that names the winning block
would make this debuggable.

**Related trap:** `openminion setup --list-providers --json` advertises
`custom-openai-compatible`, but selecting it fails at runtime with
`Unknown provider 'custom-openai-compatible'. Supported: anthropic, cerebras,
claude, cortensor, echo, groq, ollama, openai, openrouter`. The only working
path to a custom endpoint is repointing a built-in provider id (what we did).

---

## 3. `Agent.run()` returns console-rendered text, so `output_type` always fails

**Severity:** medium. The typed Python API cannot be used for structured output
on the console channel.

**Reproduce:**

```python
from pydantic import BaseModel
from openminion import Agent

class Answer(BaseModel):
    ok: bool
    value: int

with Agent(instructions="Answer in JSON.", output_type=Answer) as agent:
    result = agent.run('Return {"ok": true, "value": 42}')
```

**Observed:**

```
AgentOutputValidationError: Reply did not validate against Answer:
  Invalid JSON: expected value at line 1 column 1
  input_value='openminion: {"ok": true, "value": 42}'
```

The body is valid JSON; the literal `openminion: ` prefix from the console
renderer is what breaks `json.loads`. With `output_type` removed, the same call
returns `result.text == 'openminion: {"ok": true, "value": 42}'`, and
`result.raw["body"]` has the same prefix.

**Cause:** `api/agent.py::_coerce_output` validates `reply_text` as returned by
the console channel without stripping the channel's render prefix.

**Workaround used here:** no `output_type`; parse `result.text` with
`scout.agent.parse_json_object`, which strips `openminion:`, markdown fences,
and accepts a top-level array as well as an object.

**Suggested fix:** strip the channel prefix before coercion, or return the raw
body to the Python API and keep rendering in the CLI layer. At minimum,
document that `output_type` is not usable on the console channel.

---

## Smaller observations

- **`action_policy` blocks non-interactive tool calls.** With the default
  `require_confirm`, a scripted `Agent.run()` that triggers `fetch_page` returns
  `Policy confirmation required ... reply yes or no` as the model's answer.
  Setting `"action_policy": {"mode": "bypass"}` on the agent profile is the
  working configuration for automation. It would help to have a per-Agent or
  per-run policy override instead of a config edit.
- **Verdict stability at `temperature=0.2`.** The same three listings were
  triaged as all-`no` and all-`go` in consecutive runs. At
  `temperature=0.0` the output is stable enough to demo. Small open models need
  a one-enum output contract; a nine-field JSON verdict loses keys.
- **Console prefix affects every text consumer.** Any code that wants to parse
  `result.text` must know about `openminion: `. A `result.body` without the
  renderer prefix would remove a whole class of bugs.

## What was not tested

- Postgres storage migration parity (the repo carries a parallel
  `postgres_histories.json`; only SQLite was exercised).
- Remote/daemon runtime, ACP, browser tools, and multi-agent rooms.
- Windows. The findings above are Linux-only.

---

These notes are offered as feedback for the Hackathon #5 "What We Learned"
section. Reproductions are minimal and use only the published 0.1.17 package.
