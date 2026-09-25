#!/usr/bin/env python3
"""Build data/reading.json from the hand-written passages in reading_bank_a.py
and reading_bank_b.py (Craft and Structure, Information and Ideas, and
rhetorical synthesis). Answer positions rotate through A-D within each skill.

    python3 tools/gen_reading.py
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reading_bank_a import CRAFT  # noqa: E402
from reading_bank_b import INFO, SYNTHESIS  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "reading.json")
DOMAINS = [(CRAFT, "Craft and Structure"), (INFO, "Information and Ideas"), (SYNTHESIS, "Expression of Ideas")]

rng = random.Random(20260926)
slot, out, seen = {}, [], set()
for bank, domain in DOMAINS:
    for skill, diff, passage, question, right, wrong, why in bank:
        assert len(wrong) == 3 and len({right, *wrong}) == 4, passage[:60]
        assert passage not in seen, passage[:60]
        seen.add(passage)
        pos = slot.get(skill, 0) % 4
        slot[skill] = slot.get(skill, 0) + 1
        wrong = list(wrong)
        rng.shuffle(wrong)
        out.append({"id": f"rd-{len(out) + 1:04d}", "section": "rw", "domain": domain, "skill": skill,
                    "difficulty": diff, "passage": passage, "question": question,
                    "choices": wrong[:pos] + [right] + wrong[pos:], "answer": pos, "explanation": why})

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    from collections import Counter
    print(f"{len(out)} reading questions -> {os.path.relpath(OUT)}")
    for k, v in Counter(q["domain"] for q in out).items():
        print(f"  {v:3d}  {k}")
