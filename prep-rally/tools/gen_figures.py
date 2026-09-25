#!/usr/bin/env python3
"""Build data/figures.json: SVG figures for existing questions, plus new
questions that are answered from a figure (graphs, diagrams, charts, tables).

    python3 tools/gen_figures.py

Figures are drawn from exact coordinates here rather than pasted in, so each
one shows exactly what its question states and never gives the answer away.
Every new math answer is recomputed below and checked against its key.
"""

import json
import math
import os
from fractions import Fraction as Fr

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "figures.json")

INK = "#101827"
ACCENT = "#6D28D9"
MUTED = "#475569"
GRID = "#E2E8F0"
FONT = "Inter, ui-sans-serif, system-ui, sans-serif"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def svg(w, h, label, *parts):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{esc(label)}" font-family="{FONT}">' + "".join(parts) + "</svg>")


def line(x1, y1, x2, y2, c=INK, w=2, dash=False):
    d = ' stroke-dasharray="6 5"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{w}" stroke-linecap="round"{d}/>'


def poly(pts, c=INK, w=2, fill="none", closed=True):
    tag = "polygon" if closed else "polyline"
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return f'<{tag} points="{p}" fill="{fill}" stroke="{c}" stroke-width="{w}" stroke-linejoin="round"/>'


def text(x, y, s, anchor="middle", c=INK, size=15, italic=False, weight=500):
    style = ' font-style="italic"' if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
            f'font-size="{size}" font-weight="{weight}" fill="{c}"{style}>{esc(s)}</text>')


def dot(x, y, r=3.5, c=INK):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{c}"/>'


def circle(cx, cy, r, c=INK, w=2):
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="{c}" stroke-width="{w}"/>'


def unit(ax, ay, bx, by):
    d = math.hypot(bx - ax, by - ay)
    return (bx - ax) / d, (by - ay) / d


def right_angle(v, p, q, s=13):
    ux, uy = unit(*v, *p)
    wx, wy = unit(*v, *q)
    a = (v[0] + s * ux, v[1] + s * uy)
    b = (v[0] + s * (ux + wx), v[1] + s * (uy + wy))
    c = (v[0] + s * wx, v[1] + s * wy)
    return poly([a, b, c], w=1.6, closed=False)


def angle_mark(v, p, q, r=26, label=None, c=ACCENT, lr=None):
    """Arc at vertex v between rays toward p and q, with an optional label."""
    a1 = math.atan2(p[1] - v[1], p[0] - v[0])
    a2 = math.atan2(q[1] - v[1], q[0] - v[0])
    d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    sx, sy = v[0] + r * math.cos(a1), v[1] + r * math.sin(a1)
    ex, ey = v[0] + r * math.cos(a1 + d), v[1] + r * math.sin(a1 + d)
    out = f'<path d="M{sx:.1f},{sy:.1f} A{r},{r} 0 0 {1 if d > 0 else 0} {ex:.1f},{ey:.1f}" fill="none" stroke="{c}" stroke-width="2"/>'
    if label:
        mid = a1 + d / 2
        rr = lr or r + 16
        out += text(v[0] + rr * math.cos(mid), v[1] + rr * math.sin(mid), label, size=14, c=c, weight=600)
    return out


def mid_label(p, q, s, off=16, side=1, italic=False):
    """Label a segment at its midpoint, pushed off to one side."""
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    ux, uy = unit(*p, *q)
    nx, ny = -uy * side, ux * side
    return text(mx + off * nx, my + off * ny, s, italic=italic)


class Graph:
    """A coordinate grid mapped onto an SVG box."""

    def __init__(self, xmin, xmax, ymin, ymax, w=300, h=300, pad=26, step=1, label_every=2, ystep=None):
        self.xmin, self.xmax, self.ymin, self.ymax = xmin, xmax, ymin, ymax
        self.w, self.h, self.pad, self.step, self.every = w, h, pad, step, label_every
        self.ystep = ystep or step
        self.parts = []

    def X(self, x):
        return self.pad + (x - self.xmin) / (self.xmax - self.xmin) * (self.w - 2 * self.pad)

    def Y(self, y):
        return self.h - self.pad - (y - self.ymin) / (self.ymax - self.ymin) * (self.h - 2 * self.pad)

    def grid(self, xlabel="x", ylabel="y"):
        p = []
        x = self.xmin
        while x <= self.xmax + 1e-9:
            p.append(line(self.X(x), self.Y(self.ymin), self.X(x), self.Y(self.ymax), GRID, 1))
            x += self.step
        y = self.ymin
        while y <= self.ymax + 1e-9:
            p.append(line(self.X(self.xmin), self.Y(y), self.X(self.xmax), self.Y(y), GRID, 1))
            y += self.ystep
        p.append(line(self.X(self.xmin), self.Y(0), self.X(self.xmax), self.Y(0), INK, 1.6))
        p.append(line(self.X(0), self.Y(self.ymin), self.X(0), self.Y(self.ymax), INK, 1.6))
        k = self.xmin
        while k <= self.xmax + 1e-9:
            if k != 0 and round(k / self.step) % self.every == 0:
                p.append(text(self.X(k), self.Y(0) + 13, f"{k:g}".replace("-", "−"), size=11, c=MUTED))
            k += self.step
        k = self.ymin
        while k <= self.ymax + 1e-9:
            if k != 0 and round(k / self.ystep) % self.every == 0:
                p.append(text(self.X(0) - 6, self.Y(k), f"{k:g}".replace("-", "−"), anchor="end", size=11, c=MUTED))
            k += self.ystep
        p.append(text(self.X(self.xmax) - 2, self.Y(0) - 12, xlabel, italic=True, size=14))
        p.append(text(self.X(0) + 12, self.Y(self.ymax) + 4, ylabel, italic=True, size=14))
        p.append(text(self.X(0) - 8, self.Y(0) + 13, "O", size=11, c=MUTED))
        self.parts += p
        return self

    def curve(self, f, x0=None, x1=None, c=ACCENT, w=2.6, n=160):
        x0 = self.xmin if x0 is None else x0
        x1 = self.xmax if x1 is None else x1
        pts = []
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = f(x)
            if self.ymin - 0.5 <= y <= self.ymax + 0.5:
                pts.append((self.X(x), self.Y(max(self.ymin, min(self.ymax, y)))))
        self.parts.append(poly(pts, c=c, w=w, closed=False))
        return self

    def point(self, x, y, c=INK, r=4):
        self.parts.append(dot(self.X(x), self.Y(y), r, c))
        return self

    def render(self, label):
        return svg(self.w, self.h, label, *self.parts)


# ================================================== figures for existing questions
attach = {}

# geo-001 rectangle 8 by 5
attach["geo-001"] = svg(300, 170, "A rectangle with length 8 and width 5.",
                        poly([(40, 30), (260, 30), (260, 140), (40, 140)]),
                        text(150, 157, "8"), text(275, 85, "5"))

# right triangles with legs along the axes: (label, legs text, hyp text)
def right_tri(w_leg, h_leg, lab_w, lab_h, lab_hyp, names=None, label="A right triangle."):
    A, C, B = (50, 30), (50, 200), (50 + w_leg, 200)
    parts = [poly([A, C, B]), right_angle(C, A, B)]
    if lab_h:
        parts.append(text(A[0] - 16, (A[1] + C[1]) / 2, lab_h))
    if lab_w:
        parts.append(text((C[0] + B[0]) / 2, C[1] + 17, lab_w))
    if lab_hyp:
        parts.append(mid_label(A, B, lab_hyp, off=16, side=-1))
    if names:
        parts += [text(A[0] - 4, A[1] - 13, names[0], italic=True), text(C[0] - 14, C[1] + 12, names[1], italic=True),
                  text(B[0] + 14, B[1] + 6, names[2], italic=True)]
    return svg(50 + w_leg + 50, 230, label, *parts)


attach["geo-004"] = right_tri(226, 170, "12", "9", "?", label="A right triangle with legs 9 and 12. The hypotenuse is unknown.")
attach["geo-035"] = right_tri(226, 170, "8", "6", "?", label="A right triangle with legs 6 and 8. The hypotenuse is unknown.")
attach["geo-005"] = right_tri(226, 170, None, None, None, names=("A", "C", "B"),
                              label="Right triangle ABC with the right angle at C.")
attach["geo-028"] = right_tri(200, 170, None, None, None, names=("B", "C", "A"),
                              label="Right triangle ABC with the right angle at C.")


def thirty_sixty(label, short=None, long=None, hyp=None):
    # right angle at C, 30° at A (left), 60° at B (top)
    C, A = (260, 190), (40, 190)
    B = (260, 190 - 220 / math.sqrt(3))
    parts = [poly([A, C, B]), right_angle(C, A, B), angle_mark(A, C, B, r=34, label="30°", lr=52),
             angle_mark(B, A, C, r=22, label="60°", lr=38)]
    if long:
        parts.append(text(150, 207, long))
    if short:
        parts.append(text(276, (B[1] + C[1]) / 2, short))
    if hyp:
        parts.append(mid_label(A, B, hyp, off=15, side=-1))
    return svg(310, 225, label, *parts)


attach["geo-012"] = thirty_sixty("A 30-60-90 triangle with hypotenuse 10.", hyp="10")
attach["geo-030"] = thirty_sixty("A 30-60-90 triangle with longer leg 9.", long="9")


def box(label, a, b, c):
    f = [(40, 80), (200, 80), (200, 190), (40, 190)]
    dx, dy = 60, -45
    back = [(x + dx, y + dy) for x, y in f]
    parts = [poly(f), line(*f[0], *back[0]), line(*f[1], *back[1]), line(*f[2], *back[2]),
             poly([back[0], back[1], back[2]], closed=False),
             line(*f[3], *back[3], dash=True, c=MUTED, w=1.5), line(*back[3], *back[0], dash=True, c=MUTED, w=1.5),
             line(*back[3], *back[2], dash=True, c=MUTED, w=1.5),
             text(120, 206, a), text((f[1][0] + back[1][0]) / 2 + 26, (f[2][1] + back[2][1]) / 2 + 4, b, anchor="start"),
             text(27, 135, c)]
    return svg(300, 220, label, *parts)


attach["geo-013"] = box("A rectangular prism with edges 3, 4, and 5.", "5", "3", "4")
attach["geo-023"] = box("A rectangular box 4 feet long, 5 feet wide, and 6 feet tall.", "4", "5", "6")

# geo-007 cylinder radius 3, height 5
attach["geo-007"] = svg(240, 250, "A right circular cylinder with radius 3 and height 5.",
                        f'<ellipse cx="120" cy="50" rx="80" ry="22" fill="none" stroke="{INK}" stroke-width="2"/>',
                        f'<path d="M40,200 A80,22 0 0 0 200,200" fill="none" stroke="{INK}" stroke-width="2"/>',
                        f'<path d="M40,200 A80,22 0 0 1 200,200" fill="none" stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="6 5"/>',
                        line(40, 50, 40, 200), line(200, 50, 200, 200),
                        line(120, 50, 200, 50, ACCENT), dot(120, 50), text(160, 38, "3"),
                        text(216, 125, "5", anchor="start"))

# circles with a central angle
def central(label, r_label, angle_deg, show_arc=True, arc_label=None):
    O = (150, 130)
    R = 95
    a1 = math.radians(-20)
    a2 = a1 - math.radians(angle_deg)
    P = (O[0] + R * math.cos(a1), O[1] + R * math.sin(a1))
    Q = (O[0] + R * math.cos(a2), O[1] + R * math.sin(a2))
    parts = [circle(*O, R), line(*O, *P), line(*O, *Q), dot(*O), text(O[0] - 4, O[1] + 16, "O", italic=True),
             angle_mark(O, P, Q, r=24, label=f"{angle_deg}°", lr=42)]
    if show_arc:
        large = 1 if angle_deg > 180 else 0
        parts.append(f'<path d="M{P[0]:.1f},{P[1]:.1f} A{R},{R} 0 {large} 0 {Q[0]:.1f},{Q[1]:.1f}" fill="none" stroke="{ACCENT}" stroke-width="4"/>')
    if r_label:
        parts.append(mid_label(O, P, r_label, off=13, side=1))
    return svg(300, 250, label, *parts)


attach["geo-014"] = central("A circle with center O and radius 6. A central angle of 60 degrees intercepts the highlighted arc.", "6", 60)

# geo-021 inscribed angle
def inscribed():
    O, R = (150, 125), 95
    ang = lambda d: (O[0] + R * math.cos(math.radians(d)), O[1] + R * math.sin(math.radians(d)))
    A, B, C = ang(145), ang(35), ang(-90)
    return svg(300, 240, "Points A, B, and C on a circle with center O. Central angle AOB is 110 degrees; C is on the major arc.",
               circle(*O, R), line(*O, *A), line(*O, *B), line(*C, *A, ACCENT), line(*C, *B, ACCENT),
               dot(*O), dot(*A), dot(*B), dot(*C),
               text(O[0], O[1] - 14, "O", italic=True), text(A[0] - 12, A[1] + 8, "A", italic=True),
               text(B[0] + 12, B[1] + 8, "B", italic=True), text(C[0], C[1] - 14, "C", italic=True),
               angle_mark(O, A, B, r=22, label="110°", lr=40, c=INK))


attach["geo-021"] = inscribed()

# geo-022 chord 16 at distance 6
attach["geo-022"] = svg(300, 250, "A circle with a chord of length 16 that is 6 units from the center.",
                        circle(150, 125, 100), line(70, 185, 230, 185, ACCENT, 2.6), line(150, 125, 150, 185, INK, 1.8, dash=True),
                        right_angle((150, 185), (230, 185), (150, 125), s=11), dot(150, 125),
                        text(150, 205, "16"), text(162, 155, "6", anchor="start"))

# geo-031 parallel lines with same-side interior angles
def parallels(label, top_label, bottom_label, same_side=True):
    parts = [line(20, 70, 290, 70), line(20, 170, 290, 170),
             text(296, 70, "ℓ", anchor="start", italic=True), text(296, 170, "m", anchor="start", italic=True),
             line(90, 230, 230, 10)]
    at = lambda y: 90 + (230 - y) / 220 * 140   # where the transversal crosses height y
    t1, t2 = (at(70), 70), (at(170), 170)
    parts.append(angle_mark(t1, (290, 70), t2, r=22, label=top_label, lr=50))
    if same_side:
        parts.append(angle_mark(t2, (290, 170), t1, r=22, label=bottom_label, lr=50))
    else:
        parts.append(angle_mark(t2, (20, 170), t1, r=22, label=bottom_label, lr=50))
    return svg(320, 240, label, *parts)


attach["geo-031"] = parallels("Parallel lines l and m cut by a transversal. Two same-side interior angles are labeled.",
                              "(3x + 15)°", "(5x + 5)°")

# geo-032 exterior angle
def exterior(label, a_lab, b_lab, ext_lab):
    A, B, C = (40, 190), (230, 190), (150, 40)
    parts = [poly([A, B, C]), line(*B, 300, 190), angle_mark(B, (300, 190), C, r=26, label=ext_lab, lr=44)]
    if a_lab:
        parts.append(angle_mark(A, B, C, r=30, label=a_lab, lr=48))
    if b_lab:
        parts.append(angle_mark(C, A, B, r=24, label=b_lab, lr=42))
    return svg(320, 215, label, *parts)


attach["geo-032"] = exterior("A triangle with one side extended, forming an exterior angle of 130 degrees.", None, None, "130°")

# geo-033 triangle with DE parallel to BC
attach["geo-033"] = svg(300, 230, "Triangle ABC with D on AB and E on AC so that DE is parallel to BC. AD is 6, DB is 4, and DE is 9.",
                        poly([(150, 20), (40, 200), (270, 200)]), line(84, 128, 222, 128, ACCENT),
                        text(150, 8, "A", italic=True), text(28, 208, "B", italic=True), text(282, 208, "C", italic=True),
                        text(72, 124, "D", italic=True), text(234, 124, "E", italic=True),
                        text(104, 66, "6", anchor="end"), text(52, 162, "4", anchor="end"), text(153, 116, "9"))

# geo-034 isosceles, vertex angle 40
attach["geo-034"] = svg(260, 240, "An isosceles triangle with a vertex angle of 40 degrees.",
                        poly([(130, 20), (55, 220), (205, 220)]),
                        angle_mark((130, 20), (55, 220), (205, 220), r=34, label="40°", lr=54),
                        line(86, 116, 96, 122, INK, 2), line(164, 116, 174, 110, INK, 2))

# psd-030 scatterplot with line of best fit y = 2.4x + 15
g = Graph(0, 12, 0, 50, w=320, h=260, step=2, ystep=10, label_every=1)
g.grid("x", "y")
pts = [(1, 18), (2, 19), (3, 22.5), (4, 23), (5, 28), (6, 29), (7, 30.5), (8, 35), (9, 36), (10, 38), (11, 42)]
for x, y in pts:
    g.point(x, y, INK, 3.5)
g.curve(lambda x: 2.4 * x + 15, 0, 12)
attach["psd-030"] = g.render("A scatterplot of 11 points with a line of best fit, y = 2.4x + 15.")


# ================================================== new questions answered from a figure
new = []


def Q(qid, section, domain, skill, difficulty, question, figure, choices, answer, explanation, check=None, passage=None):
    if check is not None:
        assert choices[answer] == check, (qid, choices[answer], check)
    assert len(set(choices)) == 4
    q = {"id": qid, "section": section, "domain": domain, "skill": skill, "difficulty": difficulty,
         "question": question, "choices": choices, "answer": answer, "explanation": explanation, "figure": figure}
    if passage:
        q["passage"] = passage
    new.append(q)


G = "Geometry and Trigonometry"
A = "Advanced Math"
L = "Algebra"
P = "Problem-Solving and Data Analysis"

# F1 parallel lines, alternate interior angles 3x and 2x + 20
x = 20
assert 3 * x == 2 * x + 20
Q("fig-001", "math", G, "Parallel lines and transversals", "medium",
  "In the figure, lines ℓ and m are parallel. What is the value of x?",
  parallels("Parallel lines l and m cut by a transversal. Alternate interior angles are labeled 3x degrees and (2x + 20) degrees.",
            "3x°", "(2x + 20)°", same_side=False),
  ["20", "32", "40", "60"], 0,
  "The labeled angles are alternate interior angles, and parallel lines make them equal: 3x = 2x + 20, so x = 20. Choice D is 3x, the angle measure itself.",
  check=str(x))

# F2 exterior angle from two remote interior angles
ext = 48 + 67
Q("fig-002", "math", G, "Exterior angles", "easy",
  "In the triangle shown, what is the value of x?",
  exterior("A triangle with interior angles of 48 and 67 degrees and an exterior angle of x degrees.", "48°", "67°", "x°"),
  ["65", "115", "125", "132"], 1,
  "An exterior angle equals the sum of the two interior angles that aren't next to it: 48 + 67 = 115. Choice A is the interior angle beside it.",
  check=str(ext))

# F3 right triangle 7-24-25, sin of the angle opposite 7
hyp = math.isqrt(7 ** 2 + 24 ** 2)
fig3 = svg(330, 170, "A right triangle with legs 7 and 24. Angle x is the angle opposite the side of length 7.",
           poly([(40, 140), (290, 140), (290, 60)]), right_angle((290, 140), (40, 140), (290, 60)),
           text(165, 157, "24"), text(305, 100, "7", anchor="start"),
           angle_mark((40, 140), (290, 140), (290, 60), r=46, label="x°", lr=64))
Q("fig-003", "math", G, "Right triangle trigonometry", "medium",
  "In the right triangle shown, what is the value of sin(x°)?", fig3,
  ["7/24", "7/25", "24/25", "24/7"], 1,
  f"The hypotenuse is √(7² + 24²) = {hyp}. Sine is opposite over hypotenuse, and the side opposite angle x has length 7, so sin(x°) = 7/25. Choice A is tan(x°).",
  check=f"7/{hyp}")

# F4 arc length from a figure: radius 9, central angle 80°
arc = Fr(80, 360) * 2 * 9
Q("fig-004", "math", G, "Arc length", "medium",
  "In the circle shown, O is the center. What is the length of the highlighted arc?",
  central("A circle with center O and radius 9. A central angle of 80 degrees intercepts the highlighted arc.", "9", 80),
  ["2π", "4π", "8π", "14π"], 1,
  "The arc is 80/360 = 2/9 of the circle. The circumference is 2π(9) = 18π, so the arc length is (2/9)(18π) = 4π. Choice D is the length of the other, larger arc.",
  check=f"{arc}π")

# F5 composite figure: 10 by 6 rectangle with a semicircle on a 6-unit side
fig5 = svg(340, 180, "A 10 by 6 rectangle with a semicircle attached to its right side, which has length 6.",
           poly([(210, 30), (40, 30), (40, 132), (210, 132)], closed=False),
           f'<path d="M210,30 A51,51 0 0 1 210,132" fill="none" stroke="{INK}" stroke-width="2"/>',
           line(210, 30, 210, 132, MUTED, 1.4, dash=True), text(125, 148, "10"), text(26, 81, "6"))
area_rect, semi = 10 * 6, Fr(1, 2) * 3 ** 2
Q("fig-005", "math", G, "Area", "medium",
  "The figure shows a rectangle with a semicircle attached to one of its sides. What is the area of the figure?", fig5,
  ["60 + 4.5π", "60 + 9π", "60 + 18π", "60 + 36π"], 0,
  "The rectangle's area is 10 × 6 = 60. The semicircle has diameter 6, so its radius is 3 and its area is (1/2)π(3²) = 4.5π. The total is 60 + 4.5π. Choice B uses the whole circle.",
  check=f"{area_rect} + {float(semi):g}π")

# F6 similar triangles
def tri(ax, ay, k):
    # sides AB = 4, BC = 6, CA = 5 at k pixels per unit; C sits above A
    cx = (16 + 25 - 36) / 8        # x of C when AB lies on the x-axis
    cy = math.sqrt(25 - cx * cx)
    return (ax, ay), (ax + 4 * k, ay), (ax + cx * k, ay - cy * k)


(sa, sb, sc), (bd, be, bf) = tri(24, 170, 14), tri(140, 178, 30)
fig6 = svg(300, 205, "Triangle ABC is similar to triangle DEF. AB is 4, BC is 6, DE is 10, and EF is x.",
           poly([sa, sb, sc]), poly([bd, be, bf]),
           text(sa[0] - 6, sa[1] + 12, "A", italic=True), text(sb[0] + 8, sb[1] + 12, "B", italic=True), text(sc[0] - 4, sc[1] - 12, "C", italic=True),
           text(bd[0] - 6, bd[1] + 12, "D", italic=True), text(be[0] + 8, be[1] + 12, "E", italic=True), text(bf[0] - 4, bf[1] - 12, "F", italic=True),
           mid_label(sa, sb, "4", side=1, off=14), mid_label(sb, sc, "6", side=1, off=12),
           mid_label(bd, be, "10", side=1), mid_label(be, bf, "x", side=1, italic=True))
ef = Fr(6) * Fr(10, 4)
Q("fig-006", "math", G, "Similar triangles", "medium",
  "In the figure, triangle ABC is similar to triangle DEF, with A, B, and C corresponding to D, E, and F. What is the value of x?", fig6,
  ["12", "15", "16", "24"], 1,
  "Corresponding sides share one ratio: DE/AB = 10/4 = 2.5. So EF = 2.5 × BC = 2.5 × 6 = 15. Choice A comes from adding 6 (the difference 10 − 4) instead of multiplying.",
  check=str(ef))

# F7 equation of a graphed line through (0, -2) and (4, 4)
g = Graph(-6, 6, -6, 6).grid()
g.curve(lambda t: 1.5 * t - 2, -6, 6).point(0, -2, ACCENT).point(4, 4, ACCENT)
slope = Fr(4 - (-2), 4 - 0)
Q("fig-007", "math", L, "Linear functions", "medium",
  "Which equation defines the line shown in the xy-plane?", g.render("A line in the xy-plane passing through (0, −2) and (4, 4)."),
  ["y = (3/2)x − 2", "y = (2/3)x − 2", "y = (3/2)x + 2", "y = −(3/2)x − 2"], 0,
  "The line crosses the y-axis at (0, −2), so the y-intercept is −2. It also passes through (4, 4), so the slope is (4 − (−2))/(4 − 0) = 6/4 = 3/2. The equation is y = (3/2)x − 2.",
  check=f"y = ({slope})x − 2")

# F8 system from two graphed lines, intersecting at (3, 1)
g = Graph(-6, 6, -6, 6).grid()
g.curve(lambda t: t - 2, -6, 6).curve(lambda t: -t + 4, -6, 6, c=INK).point(3, 1, ACCENT, 5)
assert 3 - 2 == 1 and -3 + 4 == 1
Q("fig-008", "math", L, "Systems of two linear equations", "easy",
  "The graph shows a system of two linear equations. What is the solution (x, y) to the system?",
  g.render("Two lines in the xy-plane: y = x − 2 and y = −x + 4. They intersect at one point."),
  ["(1, 3)", "(3, 1)", "(0, 4)", "(2, 0)"], 1,
  "The solution to a system is the point where the graphs intersect. The lines cross at (3, 1). Choice A reverses the coordinates; choices C and D are intercepts of only one line.",
  check="(3, 1)")

# F9 parabola with zeros 0 and 4, vertex (2, -4)
g = Graph(-3, 7, -6, 6).grid()
g.curve(lambda t: t * (t - 4), -3, 7)
assert 2 * (2 - 4) == -4
Q("fig-009", "math", A, "Quadratic functions", "medium",
  "Which equation could define the graph shown in the xy-plane?",
  g.render("A parabola opening upward that crosses the x-axis at 0 and 4, with its lowest point at (2, −4)."),
  ["y = x(x + 4)", "y = x(x − 4)", "y = −x(x − 4)", "y = (x − 2)² + 4"], 1,
  "The graph crosses the x-axis at x = 0 and x = 4, so y = x(x − 4) up to a positive factor (it opens upward). Its vertex is at (2, 2(2 − 4)) = (2, −4), which matches. Choice C opens downward, and choice D has its vertex at (2, 4).")

# F10 exponential through (0, 3) and (1, 6)
g = Graph(-3, 3, -1, 13, w=300, h=300).grid()
g.curve(lambda t: 3 * 2 ** t, -3, 3).point(0, 3, ACCENT).point(1, 6, ACCENT)
Q("fig-010", "math", A, "Exponential functions", "medium",
  "The graph of y = f(x) is shown. Which equation could define f?",
  g.render("An increasing exponential curve passing through (0, 3) and (1, 6)."),
  ["f(x) = 2(3)ˣ", "f(x) = 3(2)ˣ", "f(x) = 3(0.5)ˣ", "f(x) = 6(2)ˣ"], 1,
  "The curve crosses the y-axis at (0, 3), so the starting value is 3. From x = 0 to x = 1 the value doubles from 3 to 6, so the growth factor is 2: f(x) = 3(2)ˣ. Choice A would pass through (0, 2).")

# F11 bar chart: books read, median
counts = {0: 2, 1: 5, 2: 6, 3: 4, 4: 3}
vals = [k for k, n in counts.items() for _ in range(n)]
median = (vals[9] + vals[10]) / 2
mean = sum(vals) / len(vals)
bars = []
for i, (k, n) in enumerate(counts.items()):
    x0 = 70 + i * 50
    h = n * 24
    bars.append(f'<rect x="{x0}" y="{190 - h}" width="34" height="{h}" fill="{ACCENT}" rx="2"/>')
    bars.append(text(x0 + 17, 204, str(k), size=13))
for n in range(0, 8):
    bars.insert(0, line(56, 190 - n * 24, 320, 190 - n * 24, GRID, 1))
    bars.append(text(48, 190 - n * 24, str(n), anchor="end", size=12, c=MUTED))
fig11 = svg(340, 240, "Bar graph of books read by 20 students last month: 0 books, 2 students; 1 book, 5; 2 books, 6; 3 books, 4; 4 books, 3.",
            *bars, line(56, 190, 320, 190, INK, 1.6), line(56, 190, 56, 10, INK, 1.6),
            text(188, 226, "Number of books read", size=13),
            f'<text x="0" y="0" transform="translate(18 100) rotate(-90)" text-anchor="middle" dominant-baseline="middle" font-size="13" font-weight="500" fill="{INK}">Students</text>')
Q("fig-011", "math", P, "Median of a data set", "medium",
  "The bar graph shows how many books each of 20 students read last month. What is the median number of books read?", fig11,
  ["1", "2", "2.05", "3"], 1,
  f"With 20 values, the median is the average of the 10th and 11th values in order. The first 7 students read 0 or 1 book, and the next 6 read 2, so the 10th and 11th values are both 2. Choice C is the mean, {mean:g}.",
  check=f"{median:g}")

# F12 scatterplot with a line of best fit y = 0.5x + 1
g = Graph(0, 12, 0, 8, w=320, h=240, step=1, label_every=2).grid("x", "y")
for x, y in [(1, 1.2), (2, 2.4), (3, 2.2), (4, 3.4), (5, 3.1), (6, 4.3), (7, 4.2), (8, 5.3), (9, 5.2), (10, 6.4), (11, 6.2)]:
    g.point(x, y, INK, 3.5)
g.curve(lambda t: 0.5 * t + 1, 0, 12)
Q("fig-012", "math", P, "Scatterplots and models", "easy",
  "The scatterplot shows 11 data points and a line of best fit. Based on the line of best fit, what is the predicted value of y when x = 8?",
  g.render("A scatterplot of 11 points with a line of best fit passing through (0, 1) and (12, 7)."),
  ["4", "5", "5.3", "9"], 1,
  "The line passes through (0, 1) and rises 1 unit for every 2 units of x, so it is y = 0.5x + 1. At x = 8 it predicts y = 0.5(8) + 1 = 5. Choice C is the actual data point at x = 8, not the line's prediction.",
  check=f"{0.5 * 8 + 1:g}")

# F13 two-way table: conditional probability
table = [("Grade 10", 18, 12), ("Grade 11", 24, 16)]
rows = ""
for i, (name, a, b) in enumerate(table):
    y = 73 + i * 34
    rows += text(24, y, name, anchor="start", size=14) + text(190, y, str(a), size=14) + text(290, y, str(b), size=14)
fig13 = svg(360, 175, "Table of 70 students by grade and learning preference. Grade 10: 18 online, 12 in person. Grade 11: 24 online, 16 in person.",
            f'<rect x="10" y="20" width="340" height="140" fill="none" stroke="{INK}" stroke-width="1.6" rx="6"/>',
            line(10, 56, 350, 56, INK, 1.2), line(10, 90, 350, 90, GRID, 1.2), line(140, 20, 140, 160, INK, 1.2), line(240, 20, 240, 160, GRID, 1.2),
            text(190, 38, "Online", size=14, weight=700), text(290, 38, "In person", size=14, weight=700),
            rows, line(10, 124, 350, 124, INK, 1.2), text(24, 142, "Total", anchor="start", size=14, weight=700),
            text(190, 142, "42", size=14, weight=700), text(290, 142, "28", size=14, weight=700))
p13 = Fr(16, 12 + 16)
Q("fig-013", "math", P, "Conditional probability", "medium",
  "The table shows how 70 students prefer to take a class. If a student who prefers in person is selected at random, what is the probability that the student is in grade 11?", fig13,
  ["8/35", "2/5", "3/7", "4/7"], 3,
  "Only the 28 students who prefer in person count. Of those, 16 are in grade 11, so the probability is 16/28 = 4/7. Choice A is 16/70, which uses all students, and choice C is the grade 10 share.",
  check=f"{p13.numerator}/{p13.denominator}")

# F14 Reading and Writing: data in a graph supports a claim
bars = []
data = [("City A", 30, 38), ("City B", 22, 41)]
for i, (city, y1, y2) in enumerate(data):
    x0 = 70 + i * 140
    for j, (v, col) in enumerate(((y1, "#C4B5FD"), (y2, ACCENT))):
        h = v * 3.6
        bars.append(f'<rect x="{x0 + j * 44}" y="{196 - h:.1f}" width="38" height="{h:.1f}" fill="{col}" rx="2"/>')
        bars.append(text(x0 + j * 44 + 19, 196 - h - 10, f"{v}%", size=12, weight=600))
    bars.append(text(x0 + 41, 212, city, size=13))
for v in (0, 10, 20, 30, 40, 50):
    bars.insert(0, line(56, 196 - v * 3.6, 330, 196 - v * 3.6, GRID, 1))
    bars.append(text(48, 196 - v * 3.6, f"{v}", anchor="end", size=11, c=MUTED))
fig14 = svg(350, 256, "Bar graph of the share of household waste recycled. City A: 30% in 2015 and 38% in 2020. City B: 22% in 2015 and 41% in 2020.",
            *bars, line(56, 196, 330, 196, INK, 1.6),
            f'<rect x="80" y="234" width="12" height="12" fill="#C4B5FD"/>', text(98, 240, "2015", anchor="start", size=12),
            f'<rect x="160" y="234" width="12" height="12" fill="{ACCENT}"/>', text(178, 240, "2020", anchor="start", size=12))
Q("fig-014", "rw", "Information and Ideas", "Quantitative evidence", "medium",
  "Which choice most effectively uses data from the graph to support the planner's conclusion?", fig14,
  ["City A recycled 38% of its household waste in 2020.",
   "Both cities recycled a larger share of their waste in 2020 than in 2015.",
   "City B's recycling rate rose from 22% to 41%, while City A's rose only from 30% to 38%.",
   "In 2015, City B recycled 22% of its waste, less than City A's 30%."], 2,
  "The conclusion compares how much each city improved. Choice C gives both changes (19 points for City B, 8 for City A), so it shows City B improved more. Choice B is true but doesn't compare the size of the gains.",
  passage="A city planner compared the share of household waste recycled in two cities. She concluded that City B's recycling program improved more than City A's between 2015 and 2020, even though City A started with the higher rate.")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"attach": attach, "questions": new}, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    print(f"{len(attach)} figures attached, {len(new)} new figure questions -> {os.path.relpath(OUT)}")
