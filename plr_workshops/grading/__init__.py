"""Grading for the BME 590 workshops.

`rubric.py` states what each exercise asks for; `deck.py` provides the deck
introspection those checks are written against; `scripts/grade.py` runs a
submitted notebook and reports the result.

The design decision that shapes all of it: checks encode *requirements*, not
equality with a reference solution. See rubric.py's docstring for why, and
plr-workshops-architecture.md §9 for the fuller design this is a step toward.
"""
