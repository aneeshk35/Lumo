"""Practice bots for the ranked queue.

When nobody else is searching on a ladder, the queue seats bots so a player
never waits forever. A bot plays like a person near the player's rating: it
gets easy questions right more often than hard ones, is stronger in one
section than the other, thinks for a believable amount of time, and now and
then runs out of the clock. Bots are labeled as bots everywhere they appear.

This module is pure: it decides what a bot does. server.py schedules it.
"""

import math
import os
import random

# How long a ticket waits for real players before bots fill the empty seats.
# LUMO_BOT_WAIT pins it (tests); otherwise each ticket draws its own wait so
# matches don't all land on the same beat.
BOT_WAIT_RANGE = (8.0, 13.0)
# Scales every bot thinking time. Tests run bots fast with LUMO_BOT_PACE=0.05.
BOT_PACE = float(os.environ.get("LUMO_BOT_PACE", "1") or 1)

# Rating a question "plays at" on the same scale as player Elo. A 1200 bot gets
# about 85% of easy, 60% of medium, and 35% of hard questions right.
QUESTION_RATING = {"easy": 900, "medium": 1130, "hard": 1310}
# Median seconds to answer, by difficulty, before pace scaling.
THINK_SECS = {"easy": 22, "medium": 34, "hard": 48}

NAMES = [
    "maya.k", "jordanplays", "Priya R", "ethan_w", "noor", "Leo", "sam1450",
    "ava.m", "Diego", "kenji", "hannah b", "Omar", "zoe_studies", "Rohan",
    "lily", "Marcus", "Aisha", "tyler.j", "Grace", "Nikhil", "chloe", "Mateo",
    "Isabel", "dev", "Sofia", "ben_c", "Amara", "Kai", "Nadia", "owen",
    "Ria", "Jonah", "mei", "Andre", "Tessa", "Arjun", "Luca", "Yara", "finn",
    "Hailey", "Sameer", "june", "Caleb", "Imani", "Theo", "Ananya", "Eli",
]


def bot_wait():
    pinned = os.environ.get("LUMO_BOT_WAIT")
    if pinned:
        return float(pinned)
    return random.uniform(*BOT_WAIT_RANGE)


def make_bot(rng, target_elo, taken_names):
    """A bot rated close to the player it is matched with."""
    names = [n for n in NAMES if n not in taken_names] or NAMES
    elo = int(round(target_elo + rng.gauss(0, 55)))
    elo = max(400, min(2400, elo))
    lean = rng.choice(("math", "rw"))
    return {
        "name": rng.choice(names),
        "elo": elo,
        # Stronger in one section, weaker in the other, like most students.
        "strength": {lean: elo + 60, ("rw" if lean == "math" else "math"): elo - 60},
        # Some bots are quick and a little careless, others slow and careful.
        "tempo": rng.uniform(0.75, 1.3),
        # How the bot is playing today, fixed for the whole match.
        "form": rng.gauss(0, 35),
    }


def chance_correct(bot, question):
    skill = bot["strength"].get(question["section"], bot["elo"]) + bot["form"]
    # Fast bots trade a little accuracy for speed.
    skill -= (1.0 - bot["tempo"]) * 80
    p = 1.0 / (1.0 + 10 ** ((QUESTION_RATING[question["difficulty"]] - skill) / 400.0))
    return max(0.08, min(0.96, p))


def plan_answer(bot, question, timer_ms, rng):
    """What the bot will do on this question.

    Returns {"delay": seconds, "correct": bool, "timeout": bool}. `delay` is how
    long it "thinks"; scoring uses it even if the server submits early.
    """
    median = THINK_SECS[question["difficulty"]] * bot["tempo"]
    if question.get("passage"):
        median += 6  # reading the passage takes time
    # Log-normal thinking time: mostly near the median, sometimes much longer.
    secs = median * math.exp(rng.gauss(0, 0.3))
    limit = timer_ms / 1000.0
    # A slow think usually ends in a rushed last-second answer, sometimes in
    # running out of time; and once in a while a bot just blanks.
    timeout = rng.random() < 0.02 or (secs > limit - 2 and rng.random() < 0.4)
    if secs > limit - 2:
        secs = limit - rng.uniform(2, 6)
    correct = rng.random() < chance_correct(bot, question)
    secs = max(3.0, secs)
    return {"delay": secs * BOT_PACE, "think": secs, "correct": correct, "timeout": timeout}


def pick_choice(question, correct, rng):
    """Multiple choice index, or a typed response for grid-ins."""
    if question.get("type") == "spr":
        right = question["answers"][0]
        if correct:
            return None, right
        return None, wrong_number(right, rng)
    if correct:
        return question["answer"], None
    wrong = [i for i in range(len(question["choices"])) if i != question["answer"]]
    return rng.choice(wrong), None


def wrong_number(right, rng):
    """A plausible slip: off by a small amount, a sign, or a factor of ten."""
    try:
        value = float(right.replace("−", "-").split("/")[0]) / (
            float(right.split("/")[1]) if "/" in right else 1)
    except (ValueError, ZeroDivisionError):
        return "0"
    options = [value + rng.choice((-2, -1, 1, 2)), -value if value else 1, value * 10, value / 2]
    guess = rng.choice(options)
    text = str(int(guess)) if float(guess).is_integer() else f"{guess:.2f}".rstrip("0").rstrip(".")
    return text[:6] if text != right else str(int(value) + 1)
