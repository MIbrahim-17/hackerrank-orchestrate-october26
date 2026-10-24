"""Evaluate the Haiku intent classifier on the 32 samples plus hand-written cases.

Usage: python code/evaluation/intent_eval.py [THINKING] [EFFORT]   (defaults: config.INTENT_THINKING, INTENT_EFFORT)
Every sample request is a deletion request (sample_output.csv has no NOT_APPLICABLE row), so the custom cases
carry the negative and tricky examples.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import INTENT_EFFORT, INTENT_THINKING  # noqa: E402
from data import load_requests, read_csv  # noqa: E402
from intent import classify_many  # noqa: E402

# (id, language, text, expected authorizes_deletion, expected intent)
CUSTOM_CASES = [
    ("custom_export_en", "en", "Please export all of my personal data so I can download a copy of it.", False, "DATA_EXPORT"),
    ("custom_unsubscribe_en", "en", "Unsubscribe me from your marketing emails. I don't want any more newsletters.",
     False, "MARKETING_OPT_OUT"),
    ("custom_close_keep_orders_en", "en", "Close my account, but keep my order history for my tax records.", True, "DELETION"),
    ("custom_access_fr", "fr", "Je voudrais savoir quelles données personnelles vous conservez à mon sujet.", False, "DATA_ACCESS"),
    ("custom_correction_es", "es", "He cambiado de dirección de correo electrónico; por favor, actualicen mis datos de contacto.",
     False, "CORRECTION"),
    ("custom_unsubscribe_not_delete_ja", "ja", "メールマガジンの配信を停止してください。アカウントは削除しないでください。",
     False, "MARKETING_OPT_OUT"),
]


def main(thinking: str, effort: str) -> int:
    gold = {r["case_id"]: r["deletion_status"] != "NOT_APPLICABLE" for r in read_csv("sample_output.csv")}
    items = [(r.case_id, r.request_text) for r in load_requests("sample_deletion_requests.csv")]
    items += [(cid, text) for cid, _, text, _, _ in CUSTOM_CASES]
    expected = dict(gold) | {cid: exp for cid, _, _, exp, _ in CUSTOM_CASES}
    expected_intent = {cid: intent for cid, _, _, _, intent in CUSTOM_CASES}
    start = time.time()
    results = classify_many(items, thinking=thinking, effort=effort, workers=8)
    wrong = [cid for cid in expected if results[cid]["authorizes_deletion"] != expected[cid]]
    print(f"thinking={thinking} effort={effort}  {time.time() - start:.0f}s")
    print(f"samples: {sum(results[c]['authorizes_deletion'] == gold[c] for c in gold)}/{len(gold)} correct")
    for cid, lang, text, exp, _ in CUSTOM_CASES:
        r = results[cid]
        ok = "ok " if r["authorizes_deletion"] == exp else "BAD"
        label = "ok " if r["intent"] == expected_intent[cid] else "label differs"
        print(f"  {ok} [{lang}] {cid}: expected {exp}/{expected_intent[cid]} got {r['authorizes_deletion']}/{r['intent']} ({label}) — {r['reason']}")
    print(f"overall: {len(expected) - len(wrong)}/{len(expected)} correct" + (f"; wrong: {wrong}" if wrong else ""))
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else INTENT_THINKING, sys.argv[2] if len(sys.argv) > 2 else INTENT_EFFORT))
