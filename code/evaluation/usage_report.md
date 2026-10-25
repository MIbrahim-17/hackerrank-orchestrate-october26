# Usage Report: Ghost Data Still Exists

This report covers the token usage and cost of the final full-dataset run that produced `output.csv` (518 requests), and the actual billed spend across all development.

All figures come from the call ledger in `code/llm.py` and are reproducible with:

```bash
.venv/bin/python code/evaluation/usage_ledger.py
```

The script replays the final run from the disk cache with `main.py --offline`; the replay is byte-identical to `output.csv`, which `tests/test_determinism.py` checks. It then sums the ledger. It also reads every disk-cache file, and each billed call wrote exactly one of those files.

## 1. Models and price tables

| Provider | Model | Used for | Input $/MTok | Output $/MTok | Cache read $/MTok | Cache write $/MTok | Price source and date |
|---|---|---|---|---|---|---|---|
| Anthropic | `claude-sonnet-5-5` | investigation agent (tool loop), effort medium | 2.00 | 10.00 | 0.20 | 2.50 (5-minute TTL, 1.25×) | Anthropic model table (claude-api reference, cached 2026-10-06), looked up 2026-10-24 |
| Anthropic | `claude-haiku-5-5` | intent classification (single shot, JSON schema), adaptive thinking, effort medium | 0.10 | 0.50 | 0.01 | 0.125 | Anthropic Haiku 5.5 rate card for prompts ≤ 100K tokens ($0.50 / $2.50 above), looked up 2026-10-25 |
| Google | `gemini-3.8-flash` | one-time transcription of the 11 PNG screenshots | 0.75 | 3.75 | 0.075 | — | **Promotional rate valid until 2026-12-31**, supplied 2026-10-24 |

Notes:
- Thinking tokens bill as output on every model, and the ledger counts them in "output".
- **`gemini-3.8-flash` ran on a free-tier API key.** Its cost is priced at the rates above for comparability, but **it was not charged**.
- The prices live in `code/config.py` (`PRICES`), and `llm.usage_cost()` applies them to each call.

## 2. View 1: the final full run (518 requests)

Every model call the final `output.csv` depends on, with its **original token counts** (calls served from the disk cache keep the counts of the run that first made them):

| Provider | Model | Calls | Input | Output | Cache read | Cache write | Total tokens | Cost (USD) | Tokens / request | Cost / request |
|---|---|---|---|---|---|---|---|---|---|---|
| Anthropic | claude-haiku-5-5 | 550 | 422,179 | 33,884 | 0 | 0 | 456,063 | $0.0592 | 880 | $0.000114 |
| Anthropic | claude-sonnet-5-5 | 160 | 474 | 27,057 | 420,289 | 195,368 | 643,188 | $0.8440 | 1,242 | $0.001629 |
| Google | gemini-3.8-flash | 11 | 14,337 | 8,700 | 0 | 0 | 23,037 | $0.0434 | 44 | $0.000084 |
| **All** | **Overall** | **721** | **436,990** | **69,641** | **420,289** | **195,368** | **1,122,288** | **$0.9465** | **2,167** | **$0.001827** |

Per-request figures divide by the 518 evaluation requests.

**What the calls are:**
- **Haiku, 550 intent calls:** the 518 evaluation requests plus the 32 sample requests. Intent for every known request is needed because activity-row ownership linking is global: non-deletion requests are excluded from it. Of the 550, only **398 have distinct request texts**. The other 152 repeat an identical request and reuse the same cached answer, so they were never billed separately. Counting only the 398 distinct calls: 304,129 input and 24,565 output tokens, **$0.0427**.
- **Sonnet, 160 agent calls** for the **77** routed cases: 2.08 turns per case on average, 0 retries, 77/77 submitted, 0 budget fallbacks.
- **Flash, 11 image transcriptions,** made once when the evidence index was built and reused by every case.

**Totals with each distinct call counted once:** 569 calls, 994,919 tokens, **$0.9301**, i.e. **1,921 tokens and $0.001796 per request**.

Cost split of the final run: Sonnet 89%, Haiku 6%, Flash 5% (priced, not charged).

## 3. View 2: actual billed spend across all development

Every billed call wrote exactly one disk-cache file, so the cache is the billing record. This covers all experiments, evaluation runs, the pilot, both full runs and the custom cases:

| Provider | Model | Billed calls | Input | Output | Cache read | Cache write | Total tokens | Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| Anthropic | claude-haiku-5-5 | 929 | 315,092 | 59,371 | 58,718 | 334,720 | 767,901 | $0.1036 |
| Anthropic | claude-sonnet-5-5 | 314 | 948 | 57,233 | 829,780 | 411,234 | 1,299,195 | $1.7683 |
| Google | gemini-3.8-flash | 20 | 16,627 | 9,085 | 0 | 0 | 25,712 | $0.0465 (free tier, not charged) |
| **All** | **Overall** | **1,263** | **332,667** | **125,689** | **888,498** | **745,954** | **2,092,808** | **$1.9184 priced** |

**Actually charged: $1.8719** (Anthropic only), against a self-imposed hard cap of $4.50 (`MAX_SPEND_USD`).
- The total was **$1.86** when the final `output.csv` was produced ($1.8604).
- The extra $0.058 came after it: $0.057 for the full-system sample run used in the evaluation report, and $0.0006 for the 6 custom-case intent calls.
- Development cost about twice the final run. The extra went into intent-provider and effort tuning (the Haiku calls with cache writes predate turning prompt caching off for intent), the 32-sample agent runs, the 40-case pilot, and the first 518 run before two bug fixes. That first run re-billed 8 cases.
- Gemini's 20 calls are the 11 transcriptions plus 9 intent calls from before intent moved to Haiku (the free tier allows 20 requests a day).

## 4. Token-efficiency measures

- **Deterministic pre-fetch into the first message.** Identity resolution, the gated evidence search, linked resources with their state, and every candidate's records are computed in code and placed in the agent's first message. The agent starts from facts instead of discovering them through tool calls, so it averages 2.08 turns and about 3 tool calls per case.
- **Routing only 77 of 518 cases to the agent.** The model is used only where something is genuinely undecided: a support or analytics record with no explicit category label. The deterministic validator answers the other 441 requests at no model cost. Ambiguous ownership sets were removed from routing after the agent answered "none" on 46 of 46 (9 samples, 37 pilot cases).
- **Prompt caching where it pays, not where it doesn't.** The agent loop marks its system prompt and tools for caching and caches the growing conversation, so Sonnet's input is mostly cache reads: 420,289 cache-read tokens against 474 uncached input tokens in the final run. Single-shot intent calls send no cache marker. Each request is different and the prefix is never reused, so cache writes would be pure cost. Before this change they wrote about 700 unread cache tokens per call.
- **The disk cache makes reruns free.** Every model response is stored under the hash of its exact request. The tools and the evidence index are deterministic, so an unchanged case replays its whole tool loop from disk with zero API calls. Re-runs after validator-only changes cost $0, and the final replay for this report cost $0.
- **Guard rails on spend.** The `MAX_SPEND_USD` guard refuses any live call that could push total spend over the cap and falls back to the deterministic answer; it never triggered. The files that shape model requests are frozen by hash in `tests/test_llm_guard_and_freeze.py`, so a change cannot silently re-bill cached cases.
