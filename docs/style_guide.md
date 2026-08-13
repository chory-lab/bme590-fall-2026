# Cookbook style guide

Applies to everything under `cookbook/`. Build instructions are in `cookbook/README.md`.

## Voice

**Facts and usage examples only.** State what a call does, what it returns, and what happens when
it is used wrongly. A worked example is itself the recommendation; nothing else needs to say so.

Do not write:

- judgement about what matters — "the most important chapter", "worth knowing", "the classic bug"
- narration about the text itself — "this chapter is about…", "let's be honest up front"
- claims about the reader — "this trips up nearly everyone", "you will want to"
- rhetorical framing — "the payoff", "the whole point", "honestly"

Chapters open on their first heading. No introductions.

**Second person, present tense.** "Move the lid first", not "the lid should be moved first".

## Structure

- **One heading level.** A page has its title and `##` sections. No subtitles, no `###`.
- **Callout titles use `title="…"`** so they do not enter the document outline.
- **At most two callouts per page.** A callout is for a trap that silently produces a wrong result,
  not for anything merely notable. Everything else is body text.
- **Margin notes** (`::: {.column-margin}`) for language asides. Skippable by construction — never
  put load-bearing information there.
- **Code annotations over comments** for anything needing a sentence: `# <1>` markers with a
  numbered list beneath.
- **Tabsets** for the same task on different backends or scales, not for unrelated content.

## The recipe format

A recipe is the unit of the book. Each has three parts:

1. **A statement of the task**, phrased as the reader would search for it, not as the API is named
2. **A runnable snippet**, 5–15 lines, executing against `ChatterboxBackend`
3. **See also**, pointing at related recipes and the APIs one level down

Wrap it in `::: {.recipe}` and give the heading an explicit anchor:

```markdown
## Move a plate onto a magnetic bead stand {#move-plate-to-magnet}

::: {.recipe}
...
:::
```

`part2/09_moving_labware.qmd` is the reference implementation.

Every recipe is registered in `cookbook/recipes.yml`; `path` must match the heading anchor.

## Typography

Two fonts, set in the paired themes and nowhere else: one for text, one for code. Headings use the
text face at a heavier weight — never a third family. Keep `_theme-light.scss` and
`_theme-dark.scss` structurally identical; only the palette differs.

## Accuracy

**Every API name is verified against the pinned PyLabRobot before it is written down.** The library
is mid-rename to `<vendor>_<n>_<type>_<volume>uL_<bottom>`, and deprecated shims still import and
still work, so a wrong name does not necessarily fail the build. Check the source, not your memory.

Prefer generating a fact over asserting one: `CHEATSHEET.qmd` reads signatures from the installed
package at render time, and chapter 15 prints `__abstractmethods__` rather than listing them, so
neither can drift from the version in the venv.

## Scope

The cookbook is a **standalone manual**. No exercises, no assignments, no graded content, no course
framing. Workshops link into it; nothing course-specific links out of it. Chapters 14–15 are guided
builds where every step is given, not exercises with answers withheld.
