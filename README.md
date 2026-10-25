# Ghost Data Still Exists: Deletion-Audit Agent

For every request in `dataset/deletion_requests.csv` the system decides whether the person asked for deletion. For each deletion request it finds every record of that person that existed at `audit_at`, applies `dataset/deletion_rules.csv`, and writes `output.csv` (`case_id,deletion_status,steps_json`) at the repository root.

Most of the work is deterministic. Models are used for three things only: intent classification, a one-time transcription of the 11 screenshots, and a small agent for records whose category no source states.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv venv                                   # creates .venv at the repository root
uv pip install -r code/requirements.txt   # anthropic, google-genai, pypdf, python-dotenv (pinned)
cp .env.example .env                      # then fill in the keys
```

`.env`:

```bash
ANTHROPIC_API_KEY=...   # Claude Haiku 5.5 (intent) and Claude Sonnet 5.5 (agent)
GEMINI_API_KEY=...      # Gemini 3.8 Flash (screenshot transcription); GOOGLE_API_KEY is also accepted
```

Keys are read only from the environment (`.env` is loaded by `code/config.py` and is git-ignored).

**Offline replay:** `code/cache/llm/` (about 5 MB) ships with the code. It holds every model response the final run used, stored under the hash of its exact request. With it, the full run replays **with no API keys and at $0**. Without it, a fresh run needs both keys and costs about $1 (see `code/evaluation/usage_report.md`).

## Run

```bash
.venv/bin/python code/main.py                     # all 518 requests -> output.csv (validated on write)
.venv/bin/python code/main.py --sample            # the 32 sample requests -> .cache/sample_pred.csv
.venv/bin/python code/main.py --no-llm            # deterministic baseline: no agent, no API calls (intent from cache)
.venv/bin/python code/main.py --offline           # full pipeline from the disk cache only; a cache miss is an error
.venv/bin/python code/main.py --cases case_33,case_71 --out /tmp/some.csv   # selected cases
MAX_SPEND_USD=2.00 .venv/bin/python code/main.py  # hard spend cap (default 4.50, past spend included)
```

`main.py` checks the written CSV before exiting: row count, exact header, numeric `case_id` order, no duplicates, valid JSON arrays, consecutive `step_no`, only allowed phase/operation/state combinations, `[]` for NOT_APPLICABLE, and no `evidence_id` captured after the case's `audit_at`. It exits with status 1 if any check fails.

**Budget guard:** before every live model call, `code/llm.py` adds the spend already recorded in the cache, the calls in flight, and a conservative estimate of the next call. If the total would exceed `MAX_SPEND_USD`, it makes no call and that case falls back to the deterministic answer; main.py counts and prints the fallbacks. Cache hits are always allowed.

### Evaluate and test

```bash
.venv/bin/python code/evaluation/score.py .cache/sample_pred.csv   # score against dataset/sample_output.csv
.venv/bin/python code/evaluation/score.py --custom                 # 6 synthetic end-to-end cases
.venv/bin/python code/evaluation/intent_eval.py                    # intent: 32 samples + 6 hand-written sentences
.venv/bin/python code/evaluation/usage_ledger.py                   # token and cost figures for the usage report
.venv/bin/python -m unittest discover -s code/tests                # 35 tests, incl. byte-for-byte determinism
```

## Architecture

```
request ─► intent (Haiku) ─► NOT_APPLICABLE → []
              │ deletion
              ▼
       identity (full history) ─► evidence index (94 files, gated) ─► activity-row ownership links
              │
              ▼
       routing: unlabelled support_/analytics_ record? ── yes ─► Sonnet agent (≤ 6 turns, cited choices)
              │ no                                                   │
              ▼                                                      ▼
       validator: category → state → deletion_rules.csv → steps_json (ordered, cited) ─► output.csv
```

Data flow for one case:

1. **Intent** (`code/intent.py`): Claude Haiku 5.5 classifies `request_text` in any language with a strict JSON schema (DELETION, DATA_ACCESS, DATA_EXPORT, CORRECTION, MARKETING_OPT_OUT, OTHER). Anything other than DELETION gives `NOT_APPLICABLE` with `[]`.
2. **Identity** (`code/identity.py`): the request email is resolved to a user and every email, phone and email hash the user ever held. The history comes from `user_audit_log.csv`, and email hashes are sha256 of the email. Matching is exact on normalized values.
3. **Evidence** (`code/evidence.py`): all 94 evidence files (logs in seven formats, JSON, SQL snapshots loaded into SQLite, TXT, PDFs via pypdf, screenshot transcriptions) are parsed once into per-record observations. A record counts for a case only if:
   - its file was captured at or before `audit_at`;
   - its own timestamp is at or before `audit_at`;
   - its timestamp is at or after `requested_at` (the current request, not an earlier one).

   Later evidence may only show that a record belongs to the person, never its state, and is never cited.
4. **Activity linking** (`code/activity_links.py`): some records never appear next to an identifier. They are tied to the case by the deletion worker's activity rows. The rule matches the row's time window to its wording, requires the account row's result to match `reported_status`, and assigns each row to exactly one request (constraint propagation). Rows that remain ambiguous are not guessed.
5. **Routing** (`code/main.py`): the agent runs only when the case owns a support_ or analytics_ record with no explicit category label anywhere (77 of 518). All other cases go straight to the validator.
6. **Agent** (`code/agent.py`, `code/tools.py`): Claude Sonnet 5.5 in a hand-written tool loop.
   - Its first message is pre-fetched in code: identity, linked records with their state, and candidate records.
   - It has six read-only tools, all bound to the case's time gates.
   - It may (a) categorize unlabelled support/analytics records and (b) pick from an ambiguous ownership set only by citing a record that ties the candidate to the person. Otherwise it answers "none".
   - It submits through a strict `submit_findings` schema. The validator rejects ungrounded choices as tool errors (up to 2 retries), and the loop stops after 6 turns.
7. **Validator** (`code/validator.py`): the model never writes steps. For each owned record:
   - **Category:** explicit label > agent > hint. A record naming an attachment file is a SUPPORT_ATTACHMENT label; conflicts follow a fixed priority.
   - **State:** the latest eligible observation, else absence from a full collection snapshot.
   - **Policy:** `deletion_rules.csv` gives the required end state.
   - **Steps:** a violation gives finding + remediation + verification; a compliant record gives verification only. Steps are sorted by operation order, then `system_id`, then `resource_id`.

   Findings and COMPLETE verifications cite their evidence; INCOMPLETE remediation and verification use `""`.

### Models

| Job | Model | Why |
|---|---|---|
| Intent classification | `claude-haiku-5-5`, adaptive thinking, effort medium, JSON schema | Single-shot, multilingual, about 3 s per call. Medium was the lowest setting that reached 38/38 on the samples plus 6 hand-written sentences. |
| Investigation agent | `claude-sonnet-5-5`, effort medium | Multi-turn tool use over raw evidence. Used only where a decision is open. |
| Screenshot transcription | `gemini-3.8-flash`, structured JSON | One call per screenshot (11 total), cached by image hash. |

All prompts and response schemas are in `code/prompts.py`; tool definitions are in `code/tools.py`. Every model call goes through `code/llm.py` (`call_claude`, `call_gemini`), which caches responses on disk and records model, purpose, case and token counts. Prices and their dates are in `code/config.py`.

## Results

32 public samples: status accuracy 100%, step precision 100%, recall 93.78%, F1 96.79%, sequence accuracy 65.62%, 0 wrong steps. Every sequence miss is a missing record. 6 synthetic custom cases: 6/6 pass.

## Documentation

- [code/evaluation/evaluation_report.md](code/evaluation/evaluation_report.md): accuracy, custom cases, failures found and fixes, the agent's measured contribution, limitations.
- [code/evaluation/usage_report.md](code/evaluation/usage_report.md): tokens and cost per model for the final run, and billed development spend.
- [docs/DECISIONS.md](docs/DECISIONS.md): every design decision and bug fix, with the reason and the alternatives rejected.
- [docs/inferred_rules.md](docs/inferred_rules.md): rules derived from the sample answers, each with its proving case. Where it differs from DECISIONS.md, DECISIONS.md is authoritative.

## Package

```bash
zip -r code.zip README.md code docs/DECISIONS.md docs/inferred_rules.md \
  -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```
