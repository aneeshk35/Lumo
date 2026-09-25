#!/usr/bin/env python3
"""Build data/math.json: original SAT-style math questions, mostly multiple choice
with about a quarter student-produced response (typed answers).

    python3 tools/gen_math.py

Every template covers a concept that appears on released digital SAT forms
again and again (linear equations and models, systems, quadratics, exponential
models, percents, ratios, data, right triangles, circles, volume). Numbers are
chosen so answers come out clean, answers are computed exactly with fractions,
and wrong choices come from the specific mistakes students make.
"""

import json
import os
import random
from fractions import Fraction as F

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "math.json")
ALG, ADV = "Algebra", "Advanced Math"
PSD, GEO = "Problem-Solving and Data Analysis", "Geometry and Trigonometry"

rng = random.Random(20260925)
questions = []
stems = set()
slot = {}
CURRENT = [""]          # template being run, stamped on each question as "tpl"
PASS = [0]              # pass 0 keeps each template's original fixed numbers


def fresh():
    """True after the first pass: templates with hand-picked numbers draw new ones."""
    return PASS[0] > 0


def pick_pct():
    """A percent and a base that give a whole-number answer."""
    while True:
        p = rng.choice([5, 8, 10, 12, 15, 20, 25, 30, 35, 40, 45, 60, 75])
        n = rng.choice(range(20, 401, 5))
        if p * n % 100 == 0:
            return p, n
ID_PREFIX = ["mth"]


# ------------------------------------------------------------------ formatting
def num(v):
    """Exact value as the test would print it: 7, −3, 7/2, 0.25."""
    v = F(v)
    if v.denominator == 1:
        s = str(v.numerator)
    else:
        s = f"{abs(v.numerator)}/{v.denominator}"
        if v < 0:
            s = "-" + s
    return s.replace("-", "−")


def dec(v, places=2):
    v = float(v)
    s = f"{v:,.{places}f}".rstrip("0").rstrip(".")
    return s.replace("-", "−")


def money(v):
    v = F(v)
    return f"${v.numerator // v.denominator:,}" if v.denominator == 1 else f"${float(v):,.2f}"


def poly(*terms):
    """poly((3,'x²'), (-5,'x'), (2,'')) -> '3x² − 5x + 2'."""
    out = ""
    for coef, var in terms:
        coef = F(coef)
        if coef == 0:
            continue
        mag = abs(coef)
        body = (num(mag) if (mag != 1 or not var) else "") + var
        if not out:
            out = ("−" if coef < 0 else "") + body
        else:
            out += (" − " if coef < 0 else " + ") + body
    return out or "0"


def signed(v):
    """'+ 5' or '− 5' for gluing a constant onto an expression."""
    return f"− {num(-v)}" if v < 0 else f"+ {num(v)}"


# ------------------------------------------------------------------- emitters
def _record(domain, skill, diff, question, extra):
    if question in stems:      # a later pass drew the same numbers; keep the first
        return
    stems.add(question)
    n = len(questions) + 1
    q = {"id": f"{ID_PREFIX[0]}-{n:04d}", "section": "math", "domain": domain, "skill": skill,
         "difficulty": diff, "question": question, "tpl": CURRENT[0]}
    q.update(extra)
    questions.append(q)


def mcq(domain, skill, diff, question, correct, wrongs, explanation, numeric=True):
    """Numeric choices are listed in increasing order, as on the test; text
    choices rotate the answer through A-D."""
    wrongs = [w for w in wrongs]
    choices = [correct] + wrongs
    if numeric:
        vals = [F(c) for c in choices]
        assert len(set(vals)) == 4, (question, choices)
        order = sorted(range(4), key=lambda i: vals[i])
        shown = [num(vals[i]) for i in order]
        ans = order.index(0)
    else:
        assert len(set(choices)) == 4, (question, choices)
        pos = slot.get(skill, 0) % 4
        slot[skill] = slot.get(skill, 0) + 1
        rng.shuffle(wrongs)
        shown = wrongs[:pos] + [correct] + wrongs[pos:]
        ans = pos
    _record(domain, skill, diff, question, {"choices": shown, "answer": ans, "explanation": explanation})


def spr(domain, skill, diff, question, value, explanation):
    """Typed answer. Any equivalent form is accepted by the server."""
    _record(domain, skill, diff, question,
            {"type": "spr", "choices": [], "answers": [num(value).replace("−", "-")], "explanation": explanation})


def distinct(correct, candidates, spread=(1, -1, 2, -2, 3, 5, -5, 10)):
    """Three wrong values from the mistake list, topped up if any collide."""
    out = []
    for c in candidates:
        c = F(c)
        if c != F(correct) and c not in out:
            out.append(c)
        if len(out) == 3:
            return out
    for d in spread:
        c = F(correct) + d
        if c not in out and c != F(correct):
            out.append(c)
        if len(out) == 3:
            return out
    raise AssertionError("could not build distractors")


# ===================================================================== ALGEBRA
# A1: linear equation in one variable, with distribution
def tpl_A1():
    count = 0
    tries = 0
    while count < 16 and tries < 500:
        tries += 1
        x0 = rng.choice([v for v in range(-9, 13) if v != 0])
        a, d = rng.randint(2, 8), rng.randint(1, 9)
        if a == d:
            continue
        b, c = rng.choice([v for v in range(-7, 8) if v != 0]), rng.randint(1, 15)
        e = a * (x0 + b) - c - d * x0
        if e == 0 or abs(e) > 60:
            continue
        lhs = f"{a}(x {signed(b)}) − {c}"
        rhs = poly((d, "x"), (e, ""))
        stem = f"What is the solution to the equation {lhs} = {rhs}?"
        if stem in stems:
            continue
        why = (f"Distribute: {poly((a, 'x'), (a * b, ''))} − {c} = {rhs}, so {poly((a, 'x'), (a * b - c, ''))} = {rhs}. "
               f"Subtract {d}x from both sides and move the constants: {poly((a - d, 'x'))} = {num(e - a * b + c)}, so x = {num(x0)}.")
        if count % 3 == 2:
            spr(ALG, "Linear equations in one variable", "medium", stem, x0, why)
        else:
            wrong = distinct(x0, [F(e + c - b, a - d), F(e + c + a * b, a - d), -x0, F(e - a * b - c, a - d)])
            mcq(ALG, "Linear equations in one variable", "easy" if abs(b) < 4 else "medium", stem, x0, wrong,
                why + " A common slip is multiplying only the x by " + str(a) + " and not the " + num(b) + ".")
        count += 1


# A2: cost = fixed fee + rate × quantity
def tpl_A2():
    COST = [
        ("A plumber charges a ${fee} service fee plus ${rate} per hour of work. A customer's bill was ${total}. For how many hours did the plumber work?", "hours"),
        ("A gym charges a one-time fee of ${fee} plus ${rate} per month. Dana has paid ${total} in total. For how many months has Dana been a member?", "months"),
        ("A taxi ride costs ${fee} plus ${rate} per mile. A ride cost ${total}. How many miles long was the ride?", "miles"),
        ("A moving company charges ${fee} plus ${rate} for each box it moves. A customer paid ${total}. How many boxes did the company move?", "boxes"),
        ("A bike rental shop charges ${fee} plus ${rate} per hour. A rental cost ${total}. For how many hours was the bike rented?", "hours"),
        ("A caterer charges a ${fee} setup fee plus ${rate} per guest. The bill for an event was ${total}. How many guests were at the event?", "guests"),
        ("A streaming service charges ${fee} to sign up plus ${rate} per month. A subscriber has paid ${total}. How many months has the subscriber paid for?", "months"),
        ("A printing shop charges ${fee} to set up a job plus ${rate} per poster. An order cost ${total}. How many posters were printed?", "posters"),
    ]
    for i, (tmpl, unit) in enumerate(COST):
        fee, rate, n = rng.choice([15, 20, 25, 30, 40, 45, 50, 60, 75]), rng.choice([6, 8, 9, 12, 14, 15, 18, 22, 35]), rng.randint(4, 16)
        total = fee + rate * n
        stem = tmpl.format(fee=fee, rate=rate, total=total)
        why = f"The bill is {fee} + {rate}n = {total}. Subtract {fee}: {rate}n = {total - fee}, so n = {n} {unit}."
        if i % 3 == 1:
            spr(ALG, "Linear equations in one variable", "easy", stem, n, why)
        else:
            mcq(ALG, "Linear equations in one variable", "easy", stem, n,
                distinct(n, [F(total, rate), F(total + fee, rate), n + 1, n - 2]),
                why + f" Dividing the whole bill by {rate} forgets to take off the fixed fee first.")


# A3: interpret the slope or intercept of a linear model
def tpl_A3():
    MODELS = [
        ("C = {b} + {m}h", "C", "the cost, in dollars, of renting a kayak for h hours",
         "the cost per hour to rent the kayak, in dollars", "the cost to rent the kayak before any hours are added, in dollars",
         ["the total cost of renting the kayak for {m} hours, in dollars", "the number of hours the kayak can be rented for ${b}"]),
        ("P = {b} − {m}d", "P", "the number of pages Mira has left to read d days after starting a book",
         "the number of pages Mira reads each day", "the number of pages in the book",
         ["the number of days it takes Mira to finish the book", "the number of pages Mira has left after {m} days"]),
        ("T = {b} + {m}w", "T", "the height, in centimeters, of a plant w weeks after it was measured",
         "the number of centimeters the plant grows each week", "the plant's height, in centimeters, when it was first measured",
         ["the number of weeks the plant has been growing", "the plant's height, in centimeters, after {m} weeks"]),
        ("B = {b} − {m}m", "B", "the balance, in dollars, on a gift card after m movie tickets are bought",
         "the price of one movie ticket, in dollars", "the amount on the gift card before any tickets are bought, in dollars",
         ["the number of tickets the card can buy", "the balance on the card after {m} tickets are bought, in dollars"]),
        ("W = {b} + {m}t", "W", "the amount of water, in liters, in a tank t minutes after a hose is turned on",
         "the number of liters the hose adds each minute", "the amount of water, in liters, in the tank when the hose is turned on",
         ["the number of minutes it takes to fill the tank", "the amount of water in the tank after {m} minutes, in liters"]),
        ("S = {b} + {m}y", "S", "a worker's annual salary, in dollars, y years after being hired",
         "the raise the worker receives each year, in dollars", "the worker's starting salary, in dollars",
         ["the number of years the worker has been employed", "the worker's salary after {m} years, in dollars"]),
        ("D = {b} − {m}t", "D", "a hiker's distance, in kilometers, from the end of a trail t hours after starting",
         "the number of kilometers the hiker covers each hour", "the length of the trail, in kilometers",
         ["the number of hours the hike takes", "the hiker's distance from the end of the trail after {m} hours, in kilometers"]),
        ("F = {b} + {m}n", "F", "the total fee, in dollars, for a school trip with n students",
         "the added cost, in dollars, for each student", "the cost of the trip, in dollars, before any students are counted",
         ["the number of students on the trip", "the total fee for {m} students, in dollars"]),
    ]
    for i, (form, var, meaning, slope_m, int_m, extra) in enumerate(MODELS):
        b = rng.choice([120, 150, 200, 240, 300, 350, 500]) if "−" in form else rng.choice([12, 18, 25, 30, 40, 60])
        m = rng.choice([3, 4, 5, 6, 8, 12, 15])
        if "S =" in form:
            b, m = 42000, 1500
        eq = form.format(b=f"{b:,}", m=m)
        ctx = f"The equation {eq} models {meaning}."
        wrong_pool = [e.format(m=m, b=b) for e in extra]
        mcq(ALG, "Linear functions in context", "medium", f"{ctx} What is the best interpretation of {m} in this context?",
            slope_m, [int_m] + wrong_pool, f"In a linear model, the number multiplying the variable is the rate of change. Here {m} is {slope_m}.", numeric=False)
        mcq(ALG, "Linear functions in context", "easy", f"{ctx} What is the best interpretation of {b:,} in this context?",
            int_m, [slope_m] + wrong_pool, f"The constant term is the value of {var} when the variable is 0, so {b:,} is {int_m}.", numeric=False)


# A4: linear function from two points
def tpl_A4():
    for i in range(10):
        m = rng.choice([F(v) for v in (-4, -3, -2, 2, 3, 4, 5)] + [F(1, 2), F(3, 2), F(-1, 2)])
        k = rng.randint(-8, 10)
        p, r = rng.sample(range(-4, 9), 2)
        if m.denominator == 2:
            p, r = p * 2, r * 2
        s = rng.choice([v for v in range(-6, 13) if v not in (p, r)])
        f = lambda x: m * x + k
        stem = f"For the linear function f, f({num(p)}) = {num(f(p))} and f({num(r)}) = {num(f(r))}. What is the value of f({num(s)})?"
        why = (f"The slope is (f({num(r)}) − f({num(p)}))/({num(r)} − ({num(p)})) = {num(f(r) - f(p))}/{num(r - p)} = {num(m)}. "
               f"So f(x) = {poly((m, 'x'), (k, ''))}, and f({num(s)}) = {num(f(s))}.")
        if i % 2 == 0:
            spr(ALG, "Linear functions", "medium", stem, f(s), why)
        else:
            mcq(ALG, "Linear functions", "medium", stem, f(s), distinct(f(s), [-m * s + k, m * s - k, f(s) + m, k]), why)


# A5: slope of a line in standard form, and perpendicular slope
def tpl_A5():
    for i in range(8):
        a, b = [(2, 3), (3, 4), (4, 5), (5, 2), (3, 7), (6, 5), (2, 9), (7, 4)][i]
        c = rng.choice([6, 12, 20, 24, 30, 35])
        slope = F(-a, b)
        if i % 2 == 0:
            stem = f"What is the slope of the line with equation {a}x + {b}y = {c} in the xy-plane?"
            why = f"Solve for y: {b}y = −{a}x + {c}, so y = −({a}/{b})x + {num(F(c, b))}. The slope is {num(slope)}."
            mcq(ALG, "Linear functions", "easy", stem, slope, distinct(slope, [F(a, b), F(-b, a), F(b, a)]), why + " Forgetting the negative sign gives the positive fraction.")
        else:
            stem = f"Line ℓ is perpendicular to the line {a}x + {b}y = {c} in the xy-plane. What is the slope of line ℓ?"
            why = f"The given line has slope −{a}/{b}. Perpendicular slopes are negative reciprocals, so ℓ has slope {num(F(b, a))}."
            if i % 4 == 1:
                spr(ALG, "Parallel and perpendicular lines", "medium", stem, F(b, a), why)
            else:
                mcq(ALG, "Parallel and perpendicular lines", "medium", stem, F(b, a), distinct(F(b, a), [slope, F(-b, a), F(a, b)]), why)


# A6: solve a system of two linear equations
def tpl_A6():
    for i in range(14):
        x0, y0 = rng.choice([v for v in range(-6, 10) if v]), rng.choice([v for v in range(-6, 10) if v])
        a1, b1 = rng.choice([1, 2, 3, 4]), rng.choice([-3, -2, -1, 1, 2, 3])
        a2, b2 = rng.choice([1, 2, 3, 5]), rng.choice([-4, -2, -1, 1, 3, 4])
        if a1 * b2 - a2 * b1 == 0:
            continue
        c1, c2 = a1 * x0 + b1 * y0, a2 * x0 + b2 * y0
        ask = ["x + y", "x", "y", "x − y"][i % 4]
        val = {"x + y": x0 + y0, "x": x0, "y": y0, "x − y": x0 - y0}[ask]
        stem = f"{poly((a1, 'x'), (b1, 'y'))} = {num(c1)}\n{poly((a2, 'x'), (b2, 'y'))} = {num(c2)}\nThe solution to the given system of equations is (x, y). What is the value of {ask}?"
        if stem in stems:
            continue
        why = f"Solving by elimination or substitution gives x = {num(x0)} and y = {num(y0)}, so {ask} = {num(val)}."
        if i % 3 == 0:
            spr(ALG, "Systems of two linear equations", "medium", stem, val, why)
        else:
            mcq(ALG, "Systems of two linear equations", "medium", stem, val,
                distinct(val, [y0 if ask == "x" else x0, x0 + y0 if ask != "x + y" else x0 - y0, -val, val + 2]), why)


# A7: system word problems
def tpl_A7():
    SYS = [
        ("A school sold {n} tickets to its play for a total of ${t:,}. Adult tickets cost ${p} and student tickets cost ${q}. How many student tickets were sold?", "student tickets"),
        ("A farm stand sold {n} baskets of fruit for a total of ${t:,}. Large baskets cost ${p} and small baskets cost ${q}. How many small baskets were sold?", "small baskets"),
        ("A club ordered {n} shirts for a total of ${t:,}. Long-sleeve shirts cost ${p} and short-sleeve shirts cost ${q}. How many short-sleeve shirts were ordered?", "short-sleeve shirts"),
        ("A theater sold {n} seats for a total of ${t:,}. Balcony seats cost ${p} and floor seats cost ${q}. How many floor seats were sold?", "floor seats"),
        ("A bakery sold {n} pies for a total of ${t:,}. Apple pies cost ${p} and cherry pies cost ${q}. How many cherry pies were sold?", "cherry pies"),
        ("A museum admitted {n} visitors and collected ${t:,}. Adults paid ${p} and children paid ${q}. How many children visited?", "children"),
        ("A band sold {n} items at a concert for a total of ${t:,}. Posters cost ${p} and stickers cost ${q}. How many stickers were sold?", "stickers"),
    ]
    for i, (tmpl, what) in enumerate(SYS):
        p, q = rng.choice([(12, 7), (15, 9), (20, 12), (18, 10), (9, 5), (25, 15), (14, 8)])
        big, small = rng.randint(20, 90), rng.randint(20, 90)
        n, t = big + small, big * p + small * q
        stem = tmpl.format(n=n, t=t, p=p, q=q)
        why = (f"Let a be the pricier item and s the {what}. Then a + s = {n} and {p}a + {q}s = {t:,}. "
               f"Substituting a = {n} − s gives {p * n:,} − {p - q}s = {t:,}, so s = {small}.")
        if i % 3 == 0:
            spr(ALG, "Linear systems in context", "medium", stem, small, why)
        else:
            mcq(ALG, "Linear systems in context", "medium", stem, small, distinct(small, [big, n // 2, small + (p - q)]), why + f" {big} is the number of the other item.")


# A8: systems with no solution or infinitely many solutions
def tpl_A8():
    for i in range(8):
        a, b, c = rng.choice([(2, 3, 5), (3, 4, 7), (4, 5, 9), (5, 2, 8), (3, 7, 4), (6, 5, 11), (2, 9, 13), (4, 3, 6)])
        k = rng.choice([2, 3, 4])
        if i % 2 == 0:
            d = c * k + rng.choice([1, 2, 5])
            stem = f"{a}x + {b}y = {c}\n{a * k}x + ky = {d}\nIn the given system of equations, k is a constant. For what value of k does the system have no solution?"
            why = (f"The system has no solution when the lines are parallel but different. Multiplying the first equation by {k} gives "
                   f"{a * k}x + {b * k}y = {c * k}. The x-terms match, so k = {b * k} makes the y-terms match too, and {c * k} ≠ {d}, so the lines never meet.")
            mcq(ALG, "Systems with no solution", "hard", stem, b * k, distinct(b * k, [b, d, -b * k]), why)
        else:
            stem = f"{a}x + {b}y = {c}\n{a * k}x + {b * k}y = m\nIn the given system of equations, m is a constant. For what value of m does the system have infinitely many solutions?"
            why = f"Infinitely many solutions means the two equations describe the same line. The second equation is the first multiplied by {k}, so m = {c}·{k} = {c * k}."
            if i % 4 == 1:
                spr(ALG, "Systems with infinitely many solutions", "hard", stem, c * k, why)
            else:
                mcq(ALG, "Systems with infinitely many solutions", "hard", stem, c * k, distinct(c * k, [c, c + k, c * k + k]), why)


# A9: inequality word problems (budget)
def tpl_A9():
    BUDGET = [
        ("Jalen has ${B} to spend at a fair. Admission is ${F}, and each ride ticket costs ${p}. What is the maximum number of ride tickets Jalen can buy?", "ride tickets"),
        ("A delivery van can carry at most {B} kilograms. The driver weighs {F} kilograms, and each package weighs {p} kilograms. What is the greatest number of packages the van can carry with the driver?", "packages"),
        ("A student has ${B} for school supplies. A backpack costs ${F}, and notebooks cost ${p} each. What is the greatest number of notebooks the student can buy along with the backpack?", "notebooks"),
        ("An elevator can hold at most {B} pounds. A cart weighing {F} pounds is already inside, and each box weighs {p} pounds. What is the maximum number of boxes that can be loaded?", "boxes"),
        ("Priya can spend at most ${B} on a party. The room costs ${F}, and each guest's meal costs ${p}. What is the maximum number of guests she can invite?", "guests"),
        ("A phone plan allows ${B} of charges each month. The base fee is ${F}, and each extra gigabyte costs ${p}. What is the most whole gigabytes a user can add without going over?", "gigabytes"),
    ]
    for i, (tmpl, what) in enumerate(BUDGET):
        p = rng.choice([3, 4, 6, 7, 8, 9])
        F_ = rng.choice([12, 15, 20, 25, 35])
        n = rng.randint(8, 30)
        B = F_ + p * n + rng.randint(1, p - 1)   # leaves a remainder, so rounding matters
        stem = tmpl.format(B=B, F=F_, p=p)
        why = f"{F_} + {p}n ≤ {B} gives {p}n ≤ {B - F_}, so n ≤ {dec(F(B - F_, p))}. The greatest whole number is {n}."
        if i % 2 == 0:
            spr(ALG, "Linear inequalities in context", "medium", stem, n, why)
        else:
            mcq(ALG, "Linear inequalities in context", "medium", stem, n, distinct(n, [n + 1, F(B, p) // 1, n - 1]), why + " Rounding up would go over the limit.")


# A10: solve a formula for one variable
def tpl_A10():
    FORMULAS = [
        ("A = (1/2)bh", "the area A of a triangle with base b and height h", "h", "h = 2A/b", ["h = A/(2b)", "h = 2b/A", "h = A − 2b"]),
        ("P = 2ℓ + 2w", "the perimeter P of a rectangle with length ℓ and width w", "w", "w = (P − 2ℓ)/2", ["w = P − ℓ", "w = (P − ℓ)/2", "w = P/2 − 2ℓ"]),
        ("F = (9/5)C + 32", "a temperature F in degrees Fahrenheit in terms of the temperature C in degrees Celsius", "C", "C = (5/9)(F − 32)", ["C = (9/5)(F − 32)", "C = (5/9)F − 32", "C = F − 32 − 9/5"]),
        ("V = πr²h", "the volume V of a cylinder with radius r and height h", "h", "h = V/(πr²)", ["h = πr²/V", "h = V − πr²", "h = Vπr²"]),
        ("I = Prt", "the simple interest I earned on a principal P at rate r for t years", "r", "r = I/(Pt)", ["r = IPt", "r = Pt/I", "r = I − Pt"]),
        ("v = u + at", "the velocity v of an object with starting velocity u and constant acceleration a after time t", "a", "a = (v − u)/t", ["a = v − u − t", "a = (v + u)/t", "a = t/(v − u)"]),
        ("E = (1/2)mv²", "the kinetic energy E of an object with mass m moving at speed v", "m", "m = 2E/v²", ["m = E/(2v²)", "m = 2v²/E", "m = E − v²/2"]),
    ]
    for form, what, var, right, wrong in FORMULAS:
        mcq(ADV, "Equivalent expressions", "medium",
            f"The formula {form} gives {what}. Which equation correctly expresses {var} in terms of the other variables?",
            right, wrong, f"Isolate {var} by undoing each operation on it in reverse order, doing the same thing to both sides: {right}.", numeric=False)


# ================================================================ ADVANCED MATH
# B1: quadratic solutions
def tpl_B1():
    for i in range(14):
        r1, r2 = rng.sample([v for v in range(-9, 11) if v != 0], 2)
        a = rng.choice([1, 1, 1, 2, 3])
        b, c = -a * (r1 + r2), a * r1 * r2
        eq = f"{poly((a, 'x²'), (b, 'x'), (c, ''))} = 0"
        kind = i % 4
        if kind == 0 and max(r1, r2) > 0 and min(r1, r2) < 0:
            stem = f"What is the positive solution to the equation {eq}?"
            val, why_end = max(r1, r2), f"the positive one is {max(r1, r2)}"
        elif kind == 1:
            stem = f"What is the sum of the solutions to the equation {eq}?"
            val, why_end = r1 + r2, f"their sum is {num(r1 + r2)}"
        elif kind == 2:
            stem = f"What is the product of the solutions to the equation {eq}?"
            val, why_end = r1 * r2, f"their product is {num(r1 * r2)}"
        else:
            stem = f"If x is a solution to the equation {eq} and x < {min(r1, r2) + 1}, what is the value of x?"
            val, why_end = min(r1, r2), f"the smaller one is {num(min(r1, r2))}"
        if stem in stems:
            continue
        fac = f"{'' if a == 1 else a}(x {signed(-r1)})(x {signed(-r2)})"
        why = f"Factor: {eq.replace(' = 0', '')} = {fac}, so the solutions are x = {num(r1)} and x = {num(r2)}, and {why_end}."
        if i % 3 == 0:
            spr(ADV, "Quadratic equations", "medium", stem, val, why)
        else:
            mcq(ADV, "Quadratic equations", "medium" if a == 1 else "hard", stem, val,
                distinct(val, [-val, r1 + r2 if kind != 1 else -(r1 + r2), r1 * r2 if kind != 2 else r1 + r2, F(b, a)]), why)


# B2: vertex of a parabola
def tpl_B2():
    for i in range(10):
        a = rng.choice([1, 2, 3, -1, -2])
        h, k = rng.choice([v for v in range(-6, 8) if v]), rng.choice([v for v in range(-12, 13) if v])
        while abs(h) == abs(k):
            k = rng.choice([v for v in range(-12, 13) if v])
        b, c = -2 * a * h, a * h * h + k
        expr = poly((a, "x²"), (b, "x"), (c, ""))
        if i % 2 == 0:
            what = "minimum" if a > 0 else "maximum"
            stem = f"The function f is defined by f(x) = {expr}. What is the {what} value of f(x)?"
            why = f"The vertex's x-coordinate is −b/(2a) = {num(-b)}/{num(2 * a)} = {num(h)}. Then f({num(h)}) = {num(k)}, the {what} value because the parabola opens {'up' if a > 0 else 'down'}."
            if i % 4 == 0:
                spr(ADV, "Vertex of a parabola", "hard", stem, k, why)
            else:
                mcq(ADV, "Vertex of a parabola", "hard", stem, k, distinct(k, [h, c, -k, F(-b, 2 * a) if a != 1 else h + k]), why + f" {num(h)} is where it happens, not the value itself.")
        else:
            stem = f"The graph of y = {'' if a == 1 else ('−' if a == -1 else num(a))}(x {signed(-h)})² {signed(k)} is a parabola in the xy-plane. What are the coordinates of its vertex?"
            right = f"({num(h)}, {num(k)})"
            wrong = [f"({num(-h)}, {num(k)})", f"({num(h)}, {num(-k)})", f"({num(k)}, {num(h)})"]
            mcq(ADV, "Vertex of a parabola", "easy", stem, right, wrong,
                f"In vertex form y = a(x − h)² + k, the vertex is (h, k). Here x − h is x {signed(-h)}, so h = {num(h)}, and k = {num(k)}.", numeric=False)


# B3: number of real solutions (discriminant)
def tpl_B3():
    DISC = [(1, -6, 9), (1, 4, 4), (2, -4, 2), (1, 3, 5), (2, 1, 3), (1, -2, 4), (1, 5, 3), (3, -7, 2), (1, -1, -12), (4, 4, 1)]
    for a, b, c in DISC:
        D = b * b - 4 * a * c
        right = "Exactly one" if D == 0 else ("Exactly two" if D > 0 else "Zero")
        stem = f"How many distinct real solutions does the equation {poly((a, 'x²'), (b, 'x'), (c, ''))} = 0 have?"
        mcq(ADV, "Discriminant", "medium", stem, right, [x for x in ["Exactly one", "Exactly two", "Zero", "Infinitely many"] if x != right],
            f"The discriminant is b² − 4ac = ({num(b)})² − 4({num(a)})({num(c)}) = {num(D)}. "
            + ("A discriminant of 0 means exactly one real solution." if D == 0 else
               "A positive discriminant means two real solutions." if D > 0 else "A negative discriminant means no real solutions."),
            numeric=False)


# B4: evaluate a function
def tpl_B4():
    for i in range(10):
        kind = i % 3
        if kind == 0:
            a, b, c = rng.choice([2, 3, -1, 4]), rng.randint(-6, 6), rng.randint(-9, 9)
            x = rng.choice([-3, -2, 2, 3, 4])
            val = a * x * x + b * x + c
            stem = f"The function f is defined by f(x) = {poly((a, 'x²'), (b, 'x'), (c, ''))}. What is the value of f({num(x)})?"
            why = f"Substitute {num(x)} for x: {num(a)}({num(x)})² {signed(b)}({num(x)}) {signed(c)} = {num(a * x * x)} {signed(b * x)} {signed(c)} = {num(val)}."
            wrong = [a * x * x - b * x + c, -a * x * x + b * x + c, (a * x) ** 2 + b * x + c]
        elif kind == 1:
            a, b = rng.choice([2, 3, 5]), rng.randint(1, 9)
            x = rng.choice([2, 3, 4])
            val = a ** x + b
            stem = f"The function g is defined by g(x) = {a}ˣ + {b}. What is the value of g({x})?"
            why = f"g({x}) = {a}^{x} + {b} = {a ** x} + {b} = {val}."
            wrong = [a * x + b, (a + b) ** x if (a + b) ** x < 5000 else a ** x - b, a ** (x + 1) + b]
        else:
            m, k, x = rng.choice([2, 3, 4, 5]), rng.randint(-7, 7), rng.choice([-2, 1, 3, 5])
            stem = f"The function h is defined by h(x) = {poly((m, 'x'), (k, ''))}. If h(t) = {num(m * x + k)}, what is the value of t?"
            val = x
            why = f"Set {poly((m, 'x'), (k, ''))} equal to {num(m * x + k)}: {m}t = {num(m * x)}, so t = {num(x)}."
            wrong = [m * x + k, m * (m * x + k) + k, -x]
        if i % 2 == 0:
            spr(ADV, "Function notation", "easy" if kind == 0 else "medium", stem, val, why)
        else:
            mcq(ADV, "Function notation", "easy" if kind == 0 else "medium", stem, val, distinct(val, wrong), why)


# B5: exponential growth and decay models
def tpl_B5():
    GROWTH = [
        ("The value V, in dollars, of a car t years after it was bought is modeled by V = {P:,}({f})ᵗ.", "value of the car", "decay", "year"),
        ("The population P of a town t years after 2020 is modeled by P = {P:,}({f})ᵗ.", "town's population", "growth", "year"),
        ("The number of bacteria N in a sample h hours after an experiment begins is modeled by N = {P:,}({f})ʰ.", "number of bacteria", "growth", "hour"),
        ("The mass M, in grams, of a substance d days after it was measured is modeled by M = {P:,}({f})ᵈ.", "mass of the substance", "decay", "day"),
        ("The number of subscribers S to a channel m months after launch is modeled by S = {P:,}({f})ᵐ.", "number of subscribers", "growth", "month"),
        ("The amount A, in milligrams, of a medicine in a patient's blood h hours after a dose is modeled by A = {P:,}({f})ʰ.", "amount of medicine", "decay", "hour"),
    ]
    for i, (tmpl, thing, kind, per) in enumerate(GROWTH):
        r = rng.choice([4, 5, 8, 12, 15, 20, 25])
        P = rng.choice([1200, 2500, 4000, 18000, 24000, 500, 800])
        fac = F(100 + r, 100) if kind == "growth" else F(100 - r, 100)
        f = dec(fac, 2)
        stem = tmpl.format(P=P, f=f) + f" Which statement best describes how the {thing} changes?"
        word = "increases" if kind == "growth" else "decreases"
        other = "decreases" if kind == "growth" else "increases"
        right = f"It {word} by {r}% each {per}."
        wrong = [f"It {word} by {dec(fac * 100, 0)}% each {per}.", f"It {other} by {r}% each {per}.", f"It {word} by {f} each {per}."]
        mcq(ADV, "Exponential functions", "medium", stem, right, wrong,
            f"Each {per} the {thing} is multiplied by {f}, which is {'100% + ' + str(r) + '%' if kind == 'growth' else '100% − ' + str(r) + '%'}. So it {word} by {r}% each time, not by a fixed amount.",
            numeric=False)
        start = rng.choice([1500, 2400, 3200, 6000, 750])
        r2 = rng.choice([3, 6, 7, 10, 30])
        g = F(100 + r2, 100) if kind == "growth" else F(100 - r2, 100)
        stem2 = (f"A quantity is {start:,} at time t = 0 and {'increases' if kind == 'growth' else 'decreases'} by {r2}% every year. "
                 f"Which function Q gives the quantity after t years?")
        if stem2 in stems:
            continue
        right2 = f"Q(t) = {start:,}({dec(g, 2)})ᵗ"
        wrong2 = [f"Q(t) = {start:,}({dec(F(r2, 100), 2)})ᵗ", f"Q(t) = {start:,}({dec(2 - g, 2)})ᵗ", f"Q(t) = {start:,} {'+' if kind == 'growth' else '−'} {dec(F(r2, 100), 2)}t"]
        mcq(ADV, "Exponential functions", "medium", stem2, right2, wrong2,
            f"A {r2}% {'increase' if kind == 'growth' else 'decrease'} each year multiplies the amount by {dec(g, 2)}, so Q(t) = {start:,}({dec(g, 2)})ᵗ. The last choice is linear, which adds the same amount every year.",
            numeric=False)


# B6: exponent rules
def tpl_B6():
    SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
    for i in range(8):
        a, b, c = rng.randint(2, 9), rng.randint(2, 9), rng.randint(1, 6)
        e = a + b - c
        if e in (0, 1):
            continue
        stem = f"For x > 0, the expression (x{str(a).translate(SUP)} · x{str(b).translate(SUP)}) / x{str(c).translate(SUP)} is equivalent to xⁿ. What is the value of n?"
        why = f"Multiplying powers adds exponents and dividing subtracts them: {a} + {b} − {c} = {e}."
        if i % 2 == 0:
            spr(ADV, "Exponent rules", "easy", stem, e, why)
        else:
            mcq(ADV, "Exponent rules", "easy", stem, e, distinct(e, [F(a * b, c), a * b - c, a + b + c]), why + " Multiplying the exponents is a common mistake.")
    for m, n_ in [(3, 4), (2, 5), (5, 3), (7, 2)]:
        right = f"x^({m}/{n_})"
        stem = f"For x > 0, which expression is equivalent to the {dict([(3, 'cube'), (4, 'fourth'), (5, 'fifth')]).get(n_)} root of x{str(m).translate(SUP)}?"
        if n_ == 2:
            stem = f"For x > 0, which expression is equivalent to √(x{str(m).translate(SUP)})?"
        alt = m - n_ if m - n_ not in (0, 1) else m + n_
        mcq(ADV, "Exponent rules", "medium", stem, right, [f"x^({n_}/{m})", "x" + str(m * n_).translate(SUP), "x" + str(alt).translate(SUP)],
            f"The nth root of xᵐ is x^(m/n). Here that is x^({m}/{n_}).", numeric=False)


# B7: expand products of binomials
def tpl_B7():
    for i in range(10):
        a, b, c, d = rng.choice([2, 3, 4, 5]), rng.choice([-7, -5, -3, -1, 2, 4, 6]), rng.choice([1, 2, 3]), rng.choice([-6, -4, -2, 1, 3, 5])
        p, q, r = a * c, a * d + b * c, b * d
        expr = f"({poly((a, 'x'), (b, ''))})({poly((c, 'x'), (d, ''))})"
        if i % 2 == 0:
            stem = f"The expression {expr} is equivalent to px² + qx + r, where p, q, and r are constants. What is the value of q?"
            why = f"Expanding gives {poly((p, 'x²'), (q, 'x'), (r, ''))}: the x-terms are {num(a * d)}x and {num(b * c)}x, which combine to {num(q)}x."
            val, wrong = q, [p, r, a * d]
        else:
            stem = f"If {expr} = px² + qx + r for all values of x, what is the value of p + q + r?"
            val = p + q + r
            why = f"Setting x = 1 on both sides gives p + q + r = ({num(a + b)})({num(c + d)}) = {num(val)}."
            wrong = [p + r, (a + b) + (c + d), p * r]
        if i % 3 == 0:
            spr(ADV, "Equivalent expressions", "medium", stem, val, why)
        else:
            mcq(ADV, "Equivalent expressions", "medium", stem, val, distinct(val, wrong), why)


# B8: zeros and factors
def tpl_B8():
    for i in range(8):
        r1, r2 = rng.sample([v for v in range(-8, 9) if v], 2)
        while r1 == -r2:   # opposite roots would make a "wrong" choice another real intercept
            r1, r2 = rng.sample([v for v in range(-8, 9) if v], 2)
        kind = i % 2
        f = f"(x {signed(-r1)})(x {signed(-r2)})"
        if kind == 0:
            stem = f"The function f is defined by f(x) = {f}. Which of the following is an x-intercept of the graph of y = f(x) in the xy-plane?"
            right = f"({num(r1)}, 0)"
            wrong = [f"({num(-r1)}, 0)", f"(0, {num(r1)})", f"({num(-r2)}, 0)"]
            mcq(ADV, "Quadratic functions", "easy", stem, right, wrong,
                f"f(x) = 0 when x {signed(-r1)} = 0 or x {signed(-r2)} = 0, so the x-intercepts are ({num(r1)}, 0) and ({num(r2)}, 0). The sign flips: x {signed(-r1)} is zero at x = {num(r1)}.",
                numeric=False)
        else:
            k, v = rng.choice([v for v in range(-6, 7) if v]), rng.choice([0, 0, 4, -3, 7])
            if v == 0:
                stem = f"For the polynomial p, p({num(k)}) = 0. Which of the following must be a factor of p(x)?"
                right, wrong = f"x {signed(-k)}", [f"x {signed(k)}", f"x {signed(-k - 1)}", f"{num(k)}x"]
                why = f"If p(a) = 0, then x − a is a factor. With a = {num(k)}, the factor is x {signed(-k)}."
            else:
                stem = f"For the polynomial p, p({num(k)}) = {num(v)}. What is the remainder when p(x) is divided by x {signed(-k)}?"
                why = f"The remainder when p(x) is divided by x − a is p(a). Here a = {num(k)}, so the remainder is {num(v)}."
                mcq(ADV, "Polynomial factors and remainders", "hard", stem, v, distinct(v, [k, -v, 0, -k]), why)
                continue
            mcq(ADV, "Polynomial factors and remainders", "hard", stem, right, wrong, why, numeric=False)


# B9: line meets parabola
def tpl_B9():
    for i in range(6):
        r1, r2 = rng.sample(range(-5, 7), 2)
        m, n = rng.choice([-2, -1, 1, 2, 3]), rng.randint(-5, 5)
        b, c = m - (r1 + r2), n + r1 * r2
        stem = (f"y = {poly((1, 'x²'), (b, 'x'), (c, ''))}\ny = {poly((m, 'x'), (n, ''))}\n"
                f"The graphs of the given equations intersect at two points. What is the sum of the x-coordinates of the intersection points?")
        why = f"Set the right sides equal: {poly((1, 'x²'), (b - m, 'x'), (c - n, ''))} = 0, which factors as (x {signed(-r1)})(x {signed(-r2)}) = 0. The x-coordinates are {num(r1)} and {num(r2)}, with sum {num(r1 + r2)}."
        if i % 2 == 0:
            spr(ADV, "Nonlinear systems", "hard", stem, r1 + r2, why)
        else:
            mcq(ADV, "Nonlinear systems", "hard", stem, r1 + r2, distinct(r1 + r2, [-b, -(r1 + r2), r1 * r2]), why)


# ============================================================ PROBLEM SOLVING
# C1: percentages
def tpl_C1():
    PARAMS = [(20, 45), (15, 80), (35, 60), (12, 250), (25, 64), (40, 90), (8, 150), (30, 70)]
    PCT_INC = [(10, 4500), (20, 12500), (15, 8000), (5, 3200)]
    REV = [(25, 50), (20, 96), (60, 40), (15, 69)]
    if fresh():
        PARAMS = [pick_pct() for _ in range(8)]
        PCT_INC = [(p, n * 100) for p, n in (pick_pct() for _ in range(4))]
        REV = []
        while len(REV) < 4:
            p, old = rng.choice([10, 20, 25, 50, 60, 15]), rng.choice(range(20, 201, 4))
            if old * (100 + p) % 100 == 0:
                REV.append((p, old * (100 + p) // 100))
    k = 0
    for p, n in PARAMS[:4]:
        v = F(p * n, 100)
        stem = f"What is {p}% of {n}?"
        why = f"{p}% of {n} is {p}/100 × {n} = {num(v)}."
        if k % 2 == 0:
            spr(PSD, "Percentages", "easy", stem, v, why)
        else:
            mcq(PSD, "Percentages", "easy", stem, v, distinct(v, [F(n, p), p + n, v * 10]), why)
        k += 1
    for p, n in PARAMS[4:]:
        v = F(n * (100 - p), 100)
        stem = f"A jacket originally priced at ${n} is on sale for {p}% off. What is the sale price, in dollars?"
        mcq(PSD, "Percentages", "easy", stem, v, distinct(v, [F(p * n, 100), n - p, F(n * (100 + p), 100)]),
            f"{p}% off leaves {100 - p}% of the price: {100 - p}/100 × {n} = {num(v)}. Choice {num(F(p * n, 100))} is the discount, not the sale price.")
    for p, n in PCT_INC:
        v = F(n * (100 + p), 100)
        stem = f"The number of members in a club was {n:,} last year and increased by {p}% this year. How many members does the club have this year?"
        why = f"A {p}% increase multiplies by {dec(F(100 + p, 100))}: {n:,} × {dec(F(100 + p, 100))} = {int(v):,}."
        if p % 10 == 0:
            spr(PSD, "Percent change", "easy", stem, v, why)
        else:
            mcq(PSD, "Percent change", "easy", stem, v, distinct(v, [n + p, F(n * p, 100), F(n * (100 - p), 100)]), why)
    for p, n in REV:
        v = F(n * 100, 100 + p)
        stem = f"After a {p}% increase, the price of a ticket is ${n}. What was the price, in dollars, before the increase?"
        why = f"The new price is {dec(F(100 + p, 100))} times the original, so the original is {n} ÷ {dec(F(100 + p, 100))} = {num(v)}."
        mcq(PSD, "Percent increase (reverse)", "hard", stem, v, distinct(v, [F(n * (100 - p), 100), n - p, F(n * p, 100)]),
            why + f" Taking {p}% off the new price undoes the wrong amount, because the {p}% was of the smaller original price.")
    for a, b in [(20, 25), (10, 30), (25, 20), (50, 20)]:
        v = F(100 + a, 100) * F(100 - b, 100)
        change = (v - 1) * 100
        stem = f"A store raised the price of a lamp by {a}% and later lowered the new price by {b}%. The final price is what percent of the original price?"
        why = f"Multiply the factors: {dec(F(100 + a, 100))} × {dec(F(100 - b, 100))} = {dec(v, 3)}, so the final price is {dec(v * 100)}% of the original."
        if a == 25:
            spr(PSD, "Successive percent changes", "hard", stem, v * 100, why)
        else:
            mcq(PSD, "Successive percent changes", "hard", stem, v * 100, distinct(v * 100, [100 + a - b, 100, 100 - a + b]), why + " Adding and subtracting the percents ignores that the second change applies to a different amount.")


# C2: ratios, proportions, and rates
def tpl_C2():
    RATIO = [
        ("A recipe uses {a} cups of flour for every {b} cups of sugar. How many cups of flour are needed for {c} cups of sugar?", lambda a, b, c: F(a * c, b), "{a}/{b} = f/{c}, so f = {a}·{c}/{b} = {v}."),
        ("On a map, {a} centimeters represent {b} kilometers. How many kilometers do {c} centimeters represent?", lambda a, b, c: F(b * c, a), "{b}/{a} kilometers per centimeter × {c} centimeters = {v}."),
        ("A printer prints {b} pages in {a} minutes. At this rate, how many pages does it print in {c} minutes?", lambda a, b, c: F(b * c, a), "The rate is {b}/{a} pages per minute, and {c} minutes gives {v} pages."),
        ("A car travels {b} miles on {a} gallons of gas. At this rate, how many gallons does it need to travel {c} miles?", lambda a, b, c: F(a * c, b), "The car uses {a}/{b} gallons per mile, so {c} miles needs {v} gallons."),
        ("The ratio of boys to girls in a club is {a} to {b}. If there are {c} girls, how many boys are in the club?", lambda a, b, c: F(a * c, b), "boys/girls = {a}/{b} = x/{c}, so x = {v}."),
        ("A {a}-ounce bottle of shampoo costs ${b}. At the same price per ounce, how much, in dollars, does a {c}-ounce bottle cost?", lambda a, b, c: F(b * c, a), "The price is {b}/{a} dollars per ounce, so {c} ounces cost {v} dollars."),
    ]
    RP = [(3, 2, 10), (4, 25, 18), (6, 150, 20), (5, 140, 364), (7, 4, 36), (12, 9, 20)]
    if fresh():
        RP = []
        for tmpl, fn, why in RATIO:
            while True:
                a, b, c = rng.randint(2, 12), rng.randint(2, 60), rng.randint(3, 90)
                if a != b and fn(a, b, c).denominator == 1 and fn(a, b, c) > 0:
                    RP.append((a, b, c))
                    break
    for i, ((tmpl, fn, why), (a, b, c)) in enumerate(zip(RATIO, RP)):
        v = fn(a, b, c)
        stem = tmpl.format(a=a, b=b, c=c)
        w = why.format(a=a, b=b, c=c, v=num(v))
        if i % 2 == 0:
            spr(PSD, "Ratios and proportions", "easy", stem, v, w)
        else:
            mcq(PSD, "Ratios and proportions", "easy", stem, v, distinct(v, [fn(b, a, c), c + (b - a), F(a * b, c)]), w + " Flipping the ratio is the usual mistake.")


# C3: unit conversion
def tpl_C3():
    UNITS = [
        ("A cyclist rides at {x} kilometers per hour. What is this speed in meters per minute? (1 kilometer = 1,000 meters)", lambda x: F(x * 1000, 60), [18, 24, 30], "{x} km/h = {x},000 meters per 60 minutes = {v} meters per minute."),
        ("A faucet drips {x} milliliters per minute. How many liters does it drip in one day? (1 liter = 1,000 milliliters)", lambda x: F(x * 60 * 24, 1000), [5, 25, 50], "{x} mL/min × 60 × 24 = {t:,} mL per day, which is {v} liters."),
        ("A rectangular rug is {x} feet long. How long is it in inches? (1 foot = 12 inches)", lambda x: F(x * 12), [7, 9, 11], "{x} × 12 = {v} inches."),
        ("A runner covers {x} meters per second. How many kilometers does the runner cover in one hour at this pace? (1 kilometer = 1,000 meters)", lambda x: F(x * 3600, 1000), [4, 5, 6], "{x} m/s × 3,600 seconds = {t:,} meters, or {v} kilometers."),
    ]
    for i, (tmpl, fn, xs, why) in enumerate(UNITS):
        if fresh():
            xs = rng.sample([6, 12, 18, 24, 30, 36, 42, 48, 54, 60] if i == 0 else
                            [5, 10, 15, 20, 25, 50, 75, 125] if i == 1 else
                            [3, 4, 5, 6, 8, 9, 12, 13, 15] if i == 2 else [2, 3, 4, 5, 6, 7, 8], 2)
        for j, x in enumerate(xs[:2]):
            v = fn(x)
            stem = tmpl.format(x=x)
            w = why.format(x=x, v=num(v), t=int(v * 1000))
            if (i + j) % 3 == 0:
                spr(PSD, "Unit conversion", "medium", stem, v, w)
            else:
                mcq(PSD, "Unit conversion", "medium", stem, v, distinct(v, [v * 60 if v * 60 != v else v + 7, F(v, 10), v * 10]), w)


# C4: mean and median
def tpl_C4():
    for i in range(8):
        n = rng.choice([5, 6, 7])
        data = sorted(rng.sample(range(2, 40), n))
        if i % 2 == 0:
            target = rng.randint(12, 30)
            x = target * (n + 1) - sum(data)
            if not (0 < x < 100):
                continue
            stem = f"The mean of the data set {', '.join(map(str, data))}, x is {target}. What is the value of x?"
            why = f"The {n + 1} values must total {n + 1} × {target} = {target * (n + 1)}. The known values add to {sum(data)}, so x = {x}."
            if i % 4 == 0:
                spr(PSD, "Mean of a data set", "medium", stem, x, why)
            else:
                mcq(PSD, "Mean of a data set", "medium", stem, x, distinct(x, [target * n - sum(data) if target * n - sum(data) > 0 else target, target, x + target]), why)
        else:
            med = F(data[n // 2]) if n % 2 else F(data[n // 2 - 1] + data[n // 2], 2)
            mean = F(sum(data), n)
            shuffled = data[:]
            rng.shuffle(shuffled)
            stem = f"What is the median of the data set {', '.join(map(str, shuffled))}?"
            why = f"In order the values are {', '.join(map(str, data))}. " + (f"With {n} values the median is the middle one, {num(med)}." if n % 2 else f"With {n} values the median is the average of the two middle values, {num(med)}.")
            mcq(PSD, "Median of a data set", "easy", stem, med, distinct(med, [shuffled[n // 2], mean, F(data[0] + data[-1], 2)]), why + " Taking the middle of the unsorted list is the trap.")


# C5: probability from a two-way table (described in words)
def tpl_C5():
    TABLES = [
        ("In a survey, {tot} students were asked whether they play an instrument. Of the {g1} ninth graders, {a} play an instrument; of the {g2} tenth graders, {b} play an instrument.",
         "students who play an instrument", "the student is a ninth grader", "ninth graders"),
        ("A park counted {tot} dogs. Of the {g1} large dogs, {a} were on a leash; of the {g2} small dogs, {b} were on a leash.",
         "dogs on a leash", "the dog is a large dog", "large dogs"),
        ("A cafe served {tot} customers. Of the {g1} customers who ordered coffee, {a} also bought a pastry; of the {g2} who ordered tea, {b} also bought a pastry.",
         "customers who bought a pastry", "the customer ordered coffee", "coffee drinkers"),
        ("A clinic tracked {tot} patients. Of the {g1} patients who got the new treatment, {a} improved; of the {g2} who got the standard treatment, {b} improved.",
         "patients who improved", "the patient got the new treatment", "new-treatment patients"),
        ("A school polled {tot} seniors. Of the {g1} seniors who drive to school, {a} have a part-time job; of the {g2} who take the bus, {b} have a part-time job.",
         "seniors with a part-time job", "the senior drives to school", "drivers"),
        ("An orchard picked {tot} apples. Of the {g1} red apples, {a} were bruised; of the {g2} green apples, {b} were bruised.",
         "bruised apples", "the apple is red", "red apples"),
    ]
    for i, (tmpl, pool, event, g1n) in enumerate(TABLES):
        g1, g2 = rng.choice([40, 50, 60, 80]), rng.choice([30, 40, 70, 90])
        a, b = rng.randint(8, g1 - 5), rng.randint(8, g2 - 5)
        v = F(a, a + b)
        stem = (tmpl.format(tot=g1 + g2, g1=g1, g2=g2, a=a, b=b)
                + f" If one of the {pool} is chosen at random, what is the probability that {event}?")
        why = f"Only the {a + b} {pool} count ({a} + {b}). Of those, {a} are {g1n}, so the probability is {a}/{a + b} = {num(v)}."
        if i % 3 == 0:
            spr(PSD, "Conditional probability", "hard", stem, v, why)
        else:
            mcq(PSD, "Conditional probability", "hard", stem, v, distinct(v, [F(a, g1), F(a, g1 + g2), F(b, a + b)]),
                why + f" {num(F(a, g1))} answers a different question: what fraction of the {g1n} are among the {pool}.")


# C6: estimating from a random sample
def tpl_C6():
    SAMPLES = [
        ("A random sample of {s} of the {N:,} students at a school found that {k} of them walk to school. Based on the sample, about how many students at the school walk to school?", "students"),
        ("A quality inspector randomly selected {s} of the {N:,} bolts made in one day and found {k} defective. About how many of the day's bolts are defective?", "bolts"),
        ("A random sample of {s} voters out of {N:,} registered voters in a town showed that {k} support a new library. About how many registered voters support it?", "voters"),
        ("Researchers tagged fish in a random sample of {s} from a lake with {N:,} fish and found {k} with a parasite. About how many fish in the lake have the parasite?", "fish"),
    ]
    for i, (tmpl, what) in enumerate(SAMPLES):
        s = rng.choice([40, 50, 80, 120, 200])
        N = s * rng.choice([20, 25, 30, 40, 60])
        k = rng.randint(4, s // 2)
        v = F(N * k, s)
        stem = tmpl.format(s=s, N=N, k=k)
        mcq(PSD, "Inference from a sample", "medium", stem, v, distinct(v, [k * 10, v * 2, v + s]),
            f"In the sample, {k}/{s} of the {what} have the trait. Applying that to all {N:,}: ({k}/{s}) × {N:,} = {dec(v, 1)}.")


# ================================================================== GEOMETRY
# D1: Pythagorean theorem with scaled triples
def tpl_D1():
    TRIPLES = [(3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (6, 8, 10), (9, 12, 15), (20, 21, 29), (12, 16, 20)]
    if fresh():
        TRIPLES = [tuple(k * v for v in rng.choice([(3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (20, 21, 29), (9, 40, 41)]))
                   for k in (rng.randint(1, 5) for _ in range(8))]
    for i, (a, b, c) in enumerate(TRIPLES):
        if i % 2 == 0:
            stem = f"A right triangle has legs of length {a} and {b}. What is the length of its hypotenuse?"
            val, why = c, f"c² = {a}² + {b}² = {a * a} + {b * b} = {c * c}, so c = {c}."
            wrong = [a + b, c * c, b + 1]
        else:
            stem = f"A right triangle has a hypotenuse of length {c} and one leg of length {a}. What is the length of the other leg?"
            val, why = b, f"b² = {c}² − {a}² = {c * c} − {a * a} = {b * b}, so b = {b}."
            wrong = [c - a, b * b, F(c + a, 2)]
        if i % 3 == 0:
            spr(GEO, "Right triangles", "easy", stem, val, why)
        else:
            mcq(GEO, "Right triangles", "easy", stem, val, distinct(val, wrong), why)


# D2: trig ratios from side lengths
def tpl_D2():
    tris = [(5, 12, 13), (8, 15, 17), (7, 24, 25), (3, 4, 5), (20, 21, 29), (9, 40, 41)]
    names = ["PQR"] * 6
    if fresh():
        tris = [tuple(k * v for v in rng.choice(tris)) for k in (rng.randint(1, 3) for _ in range(6))]
        names = [rng.choice(["PQR", "ABC", "JKL", "XYZ", "DEF", "RST"]) for _ in range(6)]
    for i, ((a, b, c), nm) in enumerate(zip(tris, names)):
        P, Q, R = nm
        ratio = ["sin", "cos", "tan"][i % 3] if not fresh() else rng.choice(["sin", "cos", "tan"])
        val = {"sin": F(a, c), "cos": F(b, c), "tan": F(a, b)}[ratio]
        stem = (f"In right triangle {nm}, angle {R} is the right angle, {P}{R} = {b}, {Q}{R} = {a}, and {P}{Q} = {c}. What is the value of {ratio} {P}?")
        why = (f"For angle {P}, the opposite side is {Q}{R} = {a}, the adjacent side is {P}{R} = {b}, and the hypotenuse is {P}{Q} = {c}. "
               f"{ratio} {P} = {num(val)}.")
        mcq(GEO, "Right triangle trigonometry", "medium", stem, val, distinct(val, [F(a, c), F(b, c), F(a, b), F(b, a), F(c, a)]), why)


# D3: circles in the xy-plane
def tpl_D3():
    for i in range(8):
        h, k, r = rng.choice([v for v in range(-7, 8) if v]), rng.choice([v for v in range(-7, 8) if v]), rng.choice([2, 3, 4, 5, 6, 7, 9])
        while abs(h) == abs(k):   # otherwise the swapped-coordinates choice duplicates another
            k = rng.choice([v for v in range(-7, 8) if v])
        D, E, Fc = -2 * h, -2 * k, h * h + k * k - r * r
        eq = f"x² + y² {signed(D)}x {signed(E)}y {signed(Fc)} = 0" if Fc else f"x² + y² {signed(D)}x {signed(E)}y = 0"
        if i % 2 == 0:
            stem = f"The equation {eq} defines a circle in the xy-plane. What is the radius of the circle?"
            why = f"Complete the square: (x {signed(-h)})² + (y {signed(-k)})² = {h * h} + {k * k} {signed(-Fc)} = {r * r}. The radius is √{r * r} = {r}."
            if i % 4 == 0:
                spr(GEO, "Circle equations", "hard", stem, r, why)
            else:
                mcq(GEO, "Circle equations", "hard", stem, r, distinct(r, [r * r, abs(Fc) if abs(Fc) != r else r + 3, abs(h) + abs(k)]), why)
        else:
            stem = f"The equation (x {signed(-h)})² + (y {signed(-k)})² = {r * r} defines a circle in the xy-plane. What are the coordinates of its center?"
            mcq(GEO, "Circle equations", "easy", stem, f"({num(h)}, {num(k)})",
                [f"({num(-h)}, {num(-k)})", f"({num(h)}, {num(-k)})", f"({num(k)}, {num(h)})"],
                f"A circle (x − h)² + (y − k)² = r² has center (h, k). The signs inside the parentheses are opposite the coordinates, so the center is ({num(h)}, {num(k)}).",
                numeric=False)


# D4: arc length and sector area
def tpl_D4():
    arcs = [(6, 60), (9, 120), (12, 30), (10, 72), (8, 135), (15, 48)]
    if fresh():
        arcs = [(rng.choice([3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 20]), rng.choice([20, 30, 36, 40, 45, 60, 72, 80, 90, 120, 135, 150, 240]))
                for _ in range(6)]
    for i, (r, ang) in enumerate(arcs):
        if i % 2 == 0:
            val = F(ang, 360) * 2 * r
            why = f"The arc is {ang}/360 of the circumference 2π({r}) = {2 * r}π, so its length is {num(val)}π and a = {num(val)}."
            stem = f"A circle has a radius of {r}. The length of an arc intercepted by a central angle of {ang}° is aπ. What is the value of a?"
            spr(GEO, "Arc length", "medium", stem, val, why)
        else:
            val = F(ang, 360) * r * r
            stem = f"A circle has a radius of {r}. What is the area of a sector of the circle with a central angle of {ang}°?"
            mcq(GEO, "Sector area", "medium", stem, f"{num(val)}π", [f"{num(F(ang, 360) * 2 * r)}π", f"{num(val * 2)}π", f"{r * r}π"],
                f"The sector is {ang}/360 of the circle's area π({r})² = {r * r}π, so its area is {num(val)}π. The first wrong choice is the arc length.",
                numeric=False)


# D5: volume
def tpl_D5():
    VOL = [
        ("cylinder", lambda r, h: r * r * h, "V = πr²h", "a right circular cylinder with radius {r} and height {h}"),
        ("cone", lambda r, h: F(r * r * h, 3), "V = (1/3)πr²h", "a right circular cone with radius {r} and height {h}"),
        ("sphere", lambda r, h: F(4 * r ** 3, 3), "V = (4/3)πr³", "a sphere with radius {r}"),
    ]
    for i in range(9):
        name, fn, form, desc = VOL[i % 3]
        r, h = rng.choice([3, 6, 9]) if name != "cylinder" else rng.choice([2, 3, 4, 5]), rng.choice([4, 5, 7, 8, 10])
        val = fn(r, h)
        stem = f"The volume of {desc.format(r=r, h=h)} is kπ cubic units. What is the value of k?"
        if stem in stems:
            continue
        why = f"Use {form}: " + (f"π({r})²({h}) = {num(val)}π." if name == "cylinder" else f"(1/3)π({r})²({h}) = {num(val)}π." if name == "cone" else f"(4/3)π({r})³ = {num(val)}π.")
        if i % 2 == 0:
            spr(GEO, "Volume", "medium", stem, val, why)
        else:
            wrong = [r * r * h, 2 * r * h, F(r * r * h, 3)] if name != "cone" else [r * r * h, F(r * r * h, 2), 3 * r * h]
            if name == "sphere":
                wrong = [4 * r ** 3, 4 * r * r, F(4 * r * r, 3)]
            mcq(GEO, "Volume", "medium", stem, val, distinct(val, wrong), why)


# D6: similar triangles
def tpl_D6():
    sims = [(4, 6, F(5, 2)), (6, 9, F(4, 3)), (5, 8, 3), (9, 12, F(2, 3))]
    if fresh():
        sims = []
        while len(sims) < 4:
            a, b, s = rng.randint(3, 12), rng.randint(4, 15), rng.choice([F(1, 2), F(2, 3), F(3, 2), 2, F(5, 2), 3, F(4, 3), F(3, 4)])
            if a != b and (a * s).denominator == 1 and (b * s).denominator == 1:
                sims.append((a, b, s))
    for i, (a, b, s) in enumerate(sims):
        ab2 = a * s
        val = b * s
        stem = f"Triangle ABC is similar to triangle DEF, where A corresponds to D and B corresponds to E. If AB = {a}, BC = {b}, and DE = {num(ab2)}, what is the length of EF?"
        why = f"The scale factor from ABC to DEF is DE/AB = {num(ab2)}/{a} = {num(s)}. So EF = {num(s)} × BC = {num(s)} × {b} = {num(val)}."
        if i % 2 == 0:
            spr(GEO, "Similar triangles", "medium", stem, val, why)
        else:
            mcq(GEO, "Similar triangles", "medium", stem, val, distinct(val, [b + (ab2 - a), F(b, s), a * s * s]), why + " Adding the difference instead of multiplying by the scale factor is the trap.")


# D7: angles
def tpl_D7():
    polys = [5, 6, 8, 10, 12]
    if fresh():
        polys = rng.sample([5, 6, 8, 9, 10, 12, 15, 18, 20], 5)
    for i, n in enumerate(polys):
        total = (n - 2) * 180
        each = F(total, n)
        name = {5: "pentagon", 6: "hexagon", 8: "octagon", 9: "nonagon", 10: "decagon", 12: "dodecagon"}.get(n, f"{n}-sided polygon")
        stem = f"What is the measure, in degrees, of each interior angle of a regular {name}?"
        why = f"A polygon with {n} sides has interior angles summing to ({n} − 2) × 180° = {total}°. Split evenly, each angle is {total}/{n} = {num(each)}°."
        if i % 2 == 0:
            spr(GEO, "Angle relationships", "medium", stem, each, why)
        else:
            mcq(GEO, "Angle relationships", "medium", stem, each, distinct(each, [F(360, n), 180, total]), why + " 360/n is the exterior angle, not the interior one.")


# D8: complementary angles in trigonometry
def tpl_D8():
    import math as _m
    pairs = [(28, "0.47"), (35, "0.57"), (53, "0.80"), (17, "0.29")]
    if fresh():
        pairs = [(a, f"{_m.sin(_m.radians(a)):.2f}") for a in rng.sample(range(12, 79), 4)]
    for i, (a, v) in enumerate(pairs):
        stem = f"In a right triangle, one acute angle measures {a}°, and sin({a}°) ≈ {v}. What is the approximate value of cos({90 - a}°)?"
        wrong = [f"{1 - float(v):.2f}", f"{-float(v):.2f}".replace("-", "−"), f"{float(v) / 2:.3f}".rstrip("0")]
        mcq(GEO, "Complementary angle identities", "medium", stem, v, wrong,
            f"The two acute angles of a right triangle are complementary ({a}° + {90 - a}° = 90°), and the sine of an angle equals the cosine of its complement. So cos({90 - a}°) = sin({a}°) ≈ {v}.",
            numeric=False)


# ------------------------------------------------------------------- runners
TEMPLATES = {name[4:]: fn for name, fn in list(globals().items()) if name.startswith("tpl_")}
SEED = 20260925
PASSES = 4   # each pass redraws every template's numbers; pass 1 is the original set


def build():
    """The stored bank: every template, several passes, duplicates dropped."""
    global rng
    questions.clear(); stems.clear(); slot.clear()
    ID_PREFIX[0] = "mth"
    for p in range(PASSES):
        PASS[0] = p
        rng = random.Random(SEED + p * 7919)
        for name, fn in TEMPLATES.items():
            CURRENT[0] = name
            fn()
    return list(questions)


def variants(tpl, skill=None, n=5, seed=None, avoid=()):
    """Fresh questions from one template, for "More like this". Nothing is
    stored: the server keeps them in memory for the session that asks."""
    global rng
    if tpl not in TEMPLATES:
        return []
    seed = random.randrange(1 << 30) if seed is None else seed
    found = []
    for attempt in range(6):
        questions.clear(); stems.clear(); stems.update(avoid); slot.clear()
        ID_PREFIX[0] = f"var-{seed:x}-{attempt}"
        PASS[0] = 1 + attempt
        rng = random.Random(seed + attempt)
        CURRENT[0] = tpl
        TEMPLATES[tpl]()
        for q in questions:
            if (skill is None or q["skill"] == skill) and q["question"] not in {f["question"] for f in found}:
                found.append(q)
        if len(found) >= n:
            break
    random.Random(seed).shuffle(found)
    return found[:n]


if __name__ == "__main__":
    from collections import Counter
    bank = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=1)
    n_spr = sum(1 for q in bank if q.get("type") == "spr")
    print(f"{len(bank)} math questions ({n_spr} typed-answer, {len(bank) - n_spr} multiple choice) -> {os.path.relpath(OUT)}")
    for dom, c in Counter(q["domain"] for q in bank).items():
        print(f"  {c:4d}  {dom}")
    print("  difficulty:", dict(Counter(q["difficulty"] for q in bank)))
