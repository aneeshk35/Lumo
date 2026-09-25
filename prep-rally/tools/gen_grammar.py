#!/usr/bin/env python3
"""Build data/grammar.json: about a thousand original grammar (and transition)
questions from the sentence banks in grammar_bank_a.py and grammar_bank_b.py.

    python3 tools/gen_grammar.py

Each bank entry is a sentence plus the grammatical facts about it (which clauses
are independent, what the subject's number is, and so on). This script builds
the blank, the four choices, the answer, and an explanation from those facts, so
every question in a skill is checked the same way. Output is deterministic.
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grammar_bank_a import APPOSITIVES, CLAUSES  # noqa: E402
from grammar_bank_b import (AGREEMENT, COMPLEX_LISTS, IRREGULAR_POSSESSIVES, LISTS,  # noqa: E402
                            MODIFIERS, POSSESSIVES, PRONOUNS, RESTRICTIVE, TENSE, VERB_FORMS, VERBS)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "grammar.json")
SEC = "Standard English Conventions"
EI = "Expression of Ideas"
CONV = "Which choice completes the text so that it conforms to the conventions of Standard English?"
TRANS = "Which choice completes the text with the most logical transition?"
BLANK = "______"

rng = random.Random(20260924)
questions = []
seen_passages = set()
slot = {}  # skill -> next answer position, so answers rotate A, B, C, D


def add(prefix, domain, skill, difficulty, passage, question, correct, wrongs, explanation):
    wrongs = list(wrongs)
    choices_all = [correct] + wrongs
    assert len(choices_all) == 4 and len(set(choices_all)) == 4, (skill, passage, choices_all)
    assert BLANK in passage, passage
    assert passage not in seen_passages, passage
    seen_passages.add(passage)
    pos = slot.get(skill, 0) % 4
    slot[skill] = slot.get(skill, 0) + 1
    rng.shuffle(wrongs)
    choices = wrongs[:pos] + [correct] + wrongs[pos:]
    n = sum(1 for q in questions if q["id"].startswith(prefix)) + 1
    questions.append({
        "id": f"{prefix}-{n:04d}", "section": "rw", "domain": domain, "skill": skill,
        "difficulty": difficulty, "passage": passage, "question": question,
        "choices": choices, "answer": pos, "explanation": explanation,
    })


def split_last(text):
    head, _, last = text.rpartition(" ")
    return head, last


def split_first(text):
    first, _, rest = text.partition(" ")
    return first, rest


def cap(word):
    return word[:1].upper() + word[1:]


def words(text):
    return len(text.split())


# ---------------------------------------------------------------- clauses ----
ADVERBS = {
    "contrast": ["however", "nevertheless", "even so"],
    "result": ["therefore", "as a result", "consequently"],
    "addition": ["moreover", "in addition", "furthermore"],
    "example": ["for example", "for instance"],
    "restate": ["in other words", "that is"],
}
# Transition distractors: relations that clearly do not fit. "Addition" and
# "example" are kept apart because a list of parallel facts can blur them.
DISTRACT = {
    "contrast": ["result", "addition", "example"],
    "result": ["contrast", "example", "restate"],
    "addition": ["contrast", "example", "restate"],
    "example": ["contrast", "result", "restate"],
}
RELATION_WHY = {
    "contrast": "The second sentence runs against what the first leads the reader to expect, so a contrasting transition is needed.",
    "result": "The second sentence describes a consequence of the first, so a cause-and-effect transition is needed.",
    "addition": "The second sentence adds another point of the same kind as the first, so an additive transition is needed.",
    "example": "The second sentence gives a specific case of the general claim in the first, so a transition that introduces an example is needed.",
}

for i, (a, b, rel) in enumerate(CLAUSES):
    a_head, a_last = split_last(a)
    b_first, b_rest = split_first(b)
    b_mid = b_first if b_first[0].isupper() else b_first.lower()
    total = words(a) + words(b)

    # 1. Sentence boundary: the blank spans the end of A and the start of B.
    if i % 2 == 0:
        correct, name = f"{a_last}. {cap(b_first)}", "a period"
    else:
        correct, name = f"{a_last}; {b_mid}", "a semicolon"
    add("gr", SEC, "Sentence boundaries", "easy" if total < 16 else "medium",
        f"{a_head} {BLANK} {b_rest}.", CONV, correct,
        [f"{a_last}, {b_mid}", f"{a_last} {b_mid}", f"{a_last} and {b_mid}"],
        f"Both halves are complete sentences (independent clauses), so they must be separated by {name} or joined with a comma and a conjunction. "
        f"A comma alone creates a comma splice, no punctuation creates a run-on, and \"and\" without a comma doesn't properly join two independent clauses.")

    # 2. Conjunctive adverb between two independent clauses.
    adv = ADVERBS[rel][i % len(ADVERBS[rel])]
    add("gr", SEC, "Punctuation between clauses", "hard" if "," in a or total > 22 else "medium",
        f"{a_head} {BLANK} {b}.", CONV, f"{a_last}; {adv},",
        [f"{a_last}, {adv},", f"{a_last}; {adv}", f"{a_last} {adv},"],
        f"\"{cap(adv)}\" connects two independent clauses, so it needs a semicolon before it and a comma after it. "
        f"A comma before it would create a comma splice.")

    # 3. Transition: choose the relationship between the two sentences.
    # "However" is the one contrast word that fits every contrast; the others
    # carry extra shades ("despite that") that not every pair supports.
    right = ("However" if rel == "contrast" else cap(ADVERBS[rel][(i + 1) % len(ADVERBS[rel])])) + ","
    wrong = [cap(ADVERBS[r][i % len(ADVERBS[r])]) + "," for r in DISTRACT[rel]]
    add("tr", EI, "Transitions", {"contrast": "easy", "result": "medium", "example": "medium", "addition": "medium"}[rel],
        f"{a}. {BLANK} {b}.",
        TRANS, right, wrong, f"{RELATION_WHY[rel]} \"{right[:-1]}\" signals that relationship.")

# ------------------------------------------------------------- appositives ----
for i, (subj, app, pred) in enumerate(APPOSITIVES):
    app_head, app_last = split_last(app)
    subj_head, subj_last = split_last(subj)
    long_app = words(app) > 6
    lead = f"{subj_head} " if subj_head else ""
    if i % 2 == 0:
        # closing comma after an appositive that opened with a comma
        add("gr", SEC, "Punctuating appositives", "medium",
            f"{subj}, {app_head} {BLANK} {pred}.", CONV, f"{app_last},",
            [f"{app_last}", f"{app_last};", f"{app_last}—"],
            f"\"{app}\" renames \"{subj}\" and interrupts the sentence. "
            f"It opens with a comma, so it must close with a matching comma before the verb \"{pred.split()[0]}.\"")
    else:
        # dash pair
        add("gr", SEC, "Punctuating supplementary elements", "medium",
            f"{subj}—{app_head} {BLANK} {pred}.", CONV, f"{app_last}—",
            [f"{app_last},", f"{app_last};", f"{app_last}"],
            f"The interruption \"{app}\" opens with a dash, so it must close with a dash too. "
            f"Punctuation that sets off an interruption has to come in a matching pair.")
    # opening comma
    add("gr", SEC, "Punctuating appositives", "easy",
        f"{lead}{BLANK} {app}, {pred}.", CONV, f"{subj_last},",
        [f"{subj_last}", f"{subj_last};", f"{subj_last}:"],
        f"\"{app}\" is extra information that renames the subject, and it closes with a comma, so it must open with a comma as well. "
        f"A semicolon or colon would cut the subject off from its verb, \"{pred.split()[0]}.\"")

# --------------------------------------------------------------- agreement ----
def verb_choices(verb, number):
    if verb == "be":
        return ("is", ["are", "have been", "were"]) if number == "singular" else ("are", ["is", "has been", "was"])
    s3, ing, pp = VERBS[verb]
    if number == "singular":
        return s3, [verb, f"have {pp}", f"are {ing}"]
    return verb, [s3, f"has {pp}", f"is {ing}"]


for subj, head, number, verb, rest in AGREEMENT:
    correct, wrong = verb_choices(verb, number)
    compound = " and " in head
    hard_heads = {"Each", "Neither", "one", "One", "series", "number"}
    diff = "hard" if head in hard_heads or words(subj) >= 9 else "easy" if words(subj) <= 3 else "medium"
    if compound:
        why = f"The subject is \"{head},\" two nouns joined by \"and,\" which makes it plural. The verb must be plural too: \"{correct}.\""
    else:
        why = (f"The subject is \"{head},\" which is {number}, so the verb must be {number} too: \"{correct}.\""
               + (" The words between the subject and the verb don't change the subject's number." if words(subj) > 3 else ""))
    add("gr", SEC, "Subject-verb agreement", diff, f"{subj} {BLANK} {rest}.", CONV, correct, wrong, why)

    # Same sentence, testing that nothing separates a subject from its verb.
    if "," not in subj:
        s_head, s_last = split_last(subj)
        add("gr", SEC, "Punctuation between subject and verb", "medium" if words(subj) >= 5 else "easy",
            f"{s_head} {BLANK} {correct} {rest}.", CONV, s_last,
            [f"{s_last},", f"{s_last};", f"{s_last}:"],
            f"\"{subj}\" is the subject and \"{correct}\" is its verb. No punctuation belongs between a subject and its verb, however long the subject is.")

# ---------------------------------------------------------------- pronouns ----
GROUPS = {"committee", "jury", "band", "team", "orchestra", "government", "class"}  # collective nouns
for text, ant, number, diff in PRONOUNS:
    passage = text.replace("___", BLANK)
    if number == "singular":
        extra = " A group noun like this one is treated as singular." if ant in GROUPS else ""
        add("gr", SEC, "Pronoun-antecedent agreement", diff, passage, CONV, "its", ["their", "it's", "they're"],
            f"The pronoun refers to \"{ant},\" which is singular, so it takes the singular possessive \"its.\"{extra} \"It's\" means \"it is.\"")
    else:
        add("gr", SEC, "Pronoun-antecedent agreement", diff, passage, CONV, "their", ["its", "they're", "there"],
            f"The pronoun refers to \"{ant},\" which is plural, so it takes the plural possessive \"their.\" \"They're\" means \"they are,\" and \"there\" refers to a place.")

# ------------------------------------------------------------- possessives ----
for text, sing, plur, number in POSSESSIVES:
    passage = text.replace("___", BLANK)
    if number == "singular":
        add("gr", SEC, "Possessives and contractions", "easy", passage, CONV, f"{sing}'s",
            [f"{plur}'", plur, f"{plur}'s"],
            f"The sentence refers to one {sing}, so the singular possessive \"{sing}'s\" is correct. "
            f"\"{plur}'\" shows possession by more than one {sing}, and \"{plur}\" is a plain plural that shows no possession.")
    else:
        add("gr", SEC, "Possessives and contractions", "medium", passage, CONV, f"{plur}'",
            [f"{sing}'s", plur, f"{plur}'s"],
            f"The sentence refers to more than one {sing}, so the plural possessive is needed: form the plural \"{plur}\" and add an apostrophe, \"{plur}'.\" "
            f"\"{sing}'s\" would refer to just one.")
for text, sing, plur in IRREGULAR_POSSESSIVES:
    add("gr", SEC, "Possessives and contractions", "medium", text.replace("___", BLANK), CONV, f"{plur}'s",
        [f"{plur}s'", f"{sing}'s", plur],
        f"\"{plur}\" is already plural and doesn't end in s, so its possessive is formed by adding 's: \"{plur}'s.\"")

# -------------------------------------------------------------------- tense ----
def tense_level(correct):
    if correct in ("had been analyzing", "will have finished", "will have played"):
        return "hard"
    if correct.split()[0] in ("had", "has", "have", "was", "could"):
        return "medium"
    return "easy"


for text, correct, wrong, why in TENSE:
    add("gr", SEC, "Verb tense", tense_level(correct),
        text.replace("___", BLANK), CONV, correct, wrong, why)

# -------------------------------------------------------------------- lists ----
for intro, items in LISTS:
    i_head, i_last = split_last(intro)
    series = ", ".join(items[:-1]) + ("," if len(items) > 2 else "") + " and " + items[-1]
    add("gr", SEC, "Punctuating a list", "medium", f"{i_head} {BLANK} {series}.", CONV, f"{i_last}:",
        [f"{i_last};", i_last, f"{i_last}, including:"],
        "The first part is a complete sentence that introduces a list, so a colon belongs after it. "
        "A semicolon must join two complete sentences, and a colon can't follow a word like \"including.\"")
    if len(items) >= 3:
        rest = ", ".join(items[1:-1]) + ", and " + items[-1]
        add("gr", SEC, "Punctuating a list", "easy", f"{intro}: {BLANK} {rest}.", CONV, f"{items[0]},",
            [f"{items[0]};", f"{items[0]}:", items[0]],
            "Items in a simple series are separated by commas. A semicolon is used only when the items themselves contain commas.")
for intro, items in COMPLEX_LISTS:
    (n1, d1), others = items[0], items[1:]
    tail = "; ".join(f"{n}, {d}" for n, d in others[:-1])
    tail = (tail + "; and " if tail else "and ") + f"{others[-1][0]}, {others[-1][1]}"
    d_head, d_last = split_last(d1)
    lead = f"{d_head} " if d_head else ""
    add("gr", SEC, "Punctuating a list", "hard", f"{intro}: {n1}, {lead}{BLANK} {tail}.", CONV, f"{d_last};",
        [f"{d_last},", f"{d_last}:", d_last],
        "Each item in this list already contains a comma, so the items must be separated by semicolons to keep them distinct.")

# ---------------------------------------------------------------- modifiers ----
for mod, correct, wrong in MODIFIERS:
    noun = correct.split()[1] if correct.split()[0].lower() in ("the", "a") else correct.split()[0]
    trap = any(w.split()[0 if not w.lower().startswith(("the ", "a ")) else 1].startswith(noun + "'") for w in wrong)
    add("gr", SEC, "Modifier placement", "hard" if trap else "medium", f"{mod} {BLANK}", CONV, correct, wrong,
        f"The opening phrase \"{mod[:-1]}\" describes whatever comes right after the comma. "
        f"Only this choice puts the thing it actually describes there; the others make the phrase describe the wrong noun.")

# --------------------------------------------------------------- verb forms ----
def form_level(text, correct):
    if correct.startswith("to ") or any(k in text for k in ("after ___", "for ___", "afternoon ___", "requires ___")):
        return "easy"
    if ", ___" in text or text.startswith("___"):
        return "medium"
    return "hard"   # a modifier squeezed between the subject and the main verb


for text, correct, wrong, why in VERB_FORMS:
    add("gr", SEC, "Verb forms", form_level(text, correct), text.replace("___", BLANK), CONV, correct, wrong, why)

# ------------------------------------------------------------- restrictive ----
for noun, rel, rest, pred in RESTRICTIVE:
    add("gr", SEC, "Restrictive clauses", "medium", f"{noun} {BLANK} {rest} {pred}.", CONV, rel,
        [f", {rel}", f"{rel},", f"—{rel}"],
        f"\"{rel} {rest}\" is essential: it tells the reader exactly who or what \"{noun}\" refers to. "
        f"Essential (restrictive) clauses are not set off with commas or dashes.")

# ------------------------------------------- main verb after an interruption ----
# First word of the predicate -> (plural form or None for past tense, -ing form, "to" form, past participle).
MAIN_VERB = {
    "was": ("were", "being", "to be", None), "is": ("are", "being", "to be", None), "has": ("have", "having", "to have", None),
    "forms": ("form", "forming", "to form", None), "takes": ("take", "taking", "to take", None),
    "studies": ("study", "studying", "to study", None), "completes": ("complete", "completing", "to complete", None),
    "trains": ("train", "training", "to train", None), "hosts": ("host", "hosting", "to host", None),
    "shelters": ("shelter", "sheltering", "to shelter", None), "tells": ("tell", "telling", "to tell", None),
    "fills": ("fill", "filling", "to fill", None), "appears": ("appear", "appearing", "to appear", None),
    "houses": ("house", "housing", "to house", None), "measures": ("measure", "measuring", "to measure", None),
    "leads": ("lead", "leading", "to lead", None), "gives": ("give", "giving", "to give", None),
    "circles": ("circle", "circling", "to circle", None), "draws": ("draw", "drawing", "to draw", None),
    "protects": ("protect", "protecting", "to protect", None), "attends": ("attend", "attending", "to attend", None),
    "knows": ("know", "knowing", "to know", None), "hunts": ("hunt", "hunting", "to hunt", None),
    "fools": ("fool", "fooling", "to fool", None), "hangs": ("hang", "hanging", "to hang", None),
    "bakes": ("bake", "baking", "to bake", None), "sits": ("sit", "sitting", "to sit", None),
    "shows": ("show", "showing", "to show", None), "works": ("work", "working", "to work", None),
    "holds": ("hold", "holding", "to hold", None), "supplies": ("supply", "supplying", "to supply", None),
    "sold": (None, "selling", "to sell", "sold"), "played": (None, "playing", "to play", "played"),
    "opened": (None, "opening", "to open", "opened"), "brought": (None, "bringing", "to bring", "brought"),
    "presented": (None, "presenting", "to present", "presented"), "carried": (None, "carrying", "to carry", "carried"),
    "won": (None, "winning", "to win", "won"), "grew": (None, "growing", "to grow", "grown"),
    "recommended": (None, "recommending", "to recommend", "recommended"), "scored": (None, "scoring", "to score", "scored"),
    "insisted": (None, "insisting", "to insist", "insisted"), "chose": (None, "choosing", "to choose", "chosen"),
    "visited": (None, "visiting", "to visit", "visited"), "passed": (None, "passing", "to pass", "passed"),
    "wrote": (None, "writing", "to write", "written"), "rescued": (None, "rescuing", "to rescue", "rescued"),
    "covered": (None, "covering", "to cover", "covered"), "spent": (None, "spending", "to spend", "spent"),
    "served": (None, "serving", "to serve", "served"), "added": (None, "adding", "to add", "added"),
    "included": (None, "including", "to include", "included"), "earned": (None, "earning", "to earn", "earned"),
    "fixed": (None, "fixing", "to fix", "fixed"), "answered": (None, "answering", "to answer", "answered"),
    "made": (None, "making", "to make", "made"), "started": (None, "starting", "to start", "started"),
    "attracted": (None, "attracting", "to attract", "attracted"), "designed": (None, "designing", "to design", "designed"),
}
for subj, app, pred in APPOSITIVES:
    first, rest = split_first(pred)
    if first not in MAIN_VERB or subj.endswith("results"):
        continue
    plural, ing, to, pp = MAIN_VERB[first]
    passage = f"{subj}, {app}, {BLANK} {rest}."
    long_app = words(app) >= 6
    if plural:
        add("gr", SEC, "Subject-verb agreement", "hard" if long_app else "medium", passage, CONV, first, [plural, ing, to],
            f"The subject is \"{subj},\" which is singular; \"{app}\" only renames it, so the nouns inside it don't affect the verb. "
            f"The sentence still needs a main verb that agrees with a singular subject: \"{first}.\" "
            f"\"{plural.capitalize()}\" is plural, and \"{ing}\" and \"{to}\" can't serve as a sentence's main verb.")
    else:
        add("gr", SEC, "Verb forms", "hard" if long_app else "medium", passage, CONV, first, [ing, to, f"having {pp}"],
            f"After the interruption \"{app},\" the sentence still needs a main verb for \"{subj}.\" Only \"{first}\" is a finite verb. "
            f"\"{ing.capitalize()},\" \"{to},\" and \"having {pp}\" would leave the sentence without one.")

# ---------------------------------------------------------------- write out ----
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(questions, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    from collections import Counter
    print(f"{len(questions)} questions -> {os.path.relpath(OUT)}")
    for k, v in sorted(Counter(q["skill"] for q in questions).items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    print("  difficulty:", dict(Counter(q["difficulty"] for q in questions)))
    print("  answer slots:", dict(sorted(Counter(q["answer"] for q in questions).items())))
