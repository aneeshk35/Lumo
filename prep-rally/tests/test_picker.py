#!/usr/bin/env python3
"""Checks on how sets are dealt: python3 tests/test_picker.py (no server needed)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402

failed = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def deal(section, difficulty, seen=(), count=10):
    return server.pick_questions({"section": section, "domains": [], "difficulties": [difficulty],
                                  "count": count}, seen)


for section in ("math", "rw", "mixed"):
    for difficulty in ("easy", "medium", "hard"):
        sets = [deal(section, difficulty) for _ in range(50)]
        check(f"{section}/{difficulty}: every question matches the difficulty",
              all(q["difficulty"] == difficulty for s in sets for q in s))
        check(f"{section}/{difficulty}: every question matches the section",
              all(section == "mixed" or q["section"] == section for s in sets for q in s))
        repeats = sum(len(s) - len({server.question_kind(q) for q in s}) for s in sets)
        check(f"{section}/{difficulty}: no question type repeats within a set", repeats == 0, f"{repeats} repeats")

        pool = len([q for q in server.QUESTIONS if q["difficulty"] == difficulty
                    and (section == "mixed" or q["section"] == section)])
        seen, reused = [], 0
        for _ in range(min(20, pool // 10)):
            s = deal(section, difficulty, seen)
            reused += sum(q["id"] in seen for q in s)
            seen += [q["id"] for q in s]
        check(f"{section}/{difficulty}: nothing answered comes back until the pool runs out",
              reused == 0, f"{reused} reused")

# A tiny pool still fills a set once everything has been seen.
everything = [q["id"] for q in server.QUESTIONS]
check("an exhausted pool still deals a full set", len(deal("math", "hard", everything)) == 10)

print(f"\n{'All picker checks passed' if not failed else f'{len(failed)} failed'}")
sys.exit(1 if failed else 0)
