# How Lumo rates question difficulty

Every question in the bank is labeled easy, medium, or hard. The labels drive
drills, study plans, and the separate Easy/Medium/Hard duel ladders, so they
have to mean the same thing everywhere. Rate the question, not the topic.

## Easy
One step, or a fact you recognize on sight.
- Math: evaluate f(3), find 15% of 60, the hypotenuse of a 6-8-10 triangle,
  read a vertex off vertex form, read a value off a graph.
- Reading and writing: a word whose meaning the sentence spells out, a plain
  comma in a list, an infinitive after "decided" or "plans".

## Medium
Two or three routine steps, or turning words into an equation.
- Math: solve an equation with distribution on both sides, a system of two
  equations, a percent increase in reverse, a conditional probability from a
  table, completing the square to find a vertex.
- Reading and writing: a main idea, a transition with a clear relationship,
  matching punctuation around an appositive, a past-perfect tense cue.

## Hard
Something that trips up a student who knows the rule. At least one of:
- **A parameter**: solve for a constant that makes graphs touch, a system
  have no solution, or a polynomial have a factor.
- **A trap to reject**: an extraneous root, a scale factor that must be
  cubed, a possessive that hides the right noun in a modifier question.
- **An insight**: a structural shortcut (complementary angles, sum and
  difference of constants, rewriting an exponential for a new time unit).
- **Chained ideas**: several concepts in sequence (surface area to edge to a
  scaled volume; slope to perpendicular slope to intercept).
- Reading and writing: a long interruption between subject and verb,
  "each/neither" subjects, semicolons in a list of items with commas,
  "however" in the middle of a clause, reasoning that rules out an
  alternative explanation or combines several findings.

A long question is not automatically hard, and an unfamiliar topic is not
automatically hard. If a hard label can't point to one of the reasons above,
it is medium.

## Where the labels live
- `data/questions.json`: hand-labeled.
- `tools/gen_math.py`, `tools/gen_grammar.py`: set per template, with
  feature-based rules; the `hard_*` math templates are the hard set.
- `tools/reading_bank_*.py`, `tools/gen_figures.py`: set per item.
