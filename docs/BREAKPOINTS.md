# Argus Breakpoints

Status: Active Alpha implementation

`.agent/designs/argus/DESIGN.md` section 8 fixes the width bands. This page says
what each band means and what the shell actually changes at it. It is
deliberately not a catalogue of views. A catalogue goes stale the day it lands
and gives false confidence in the meantime.

**Doc for intent, baselines for fact.** If this page and a baseline disagree,
the baseline is right and this page is out of date.

## The bands

| Band | Width | What the shell does |
|------|-------|---------------------|
| Mobile Small | <400px | Same shell as Mobile. Nothing branches here; it is the width the type scale is written from. |
| Mobile | 400 to 720px | Navigation lives in a drawer behind the top bar. No activity rail. Omnisearch is a single list; a dossier opens as a sheet on top of it. Settings is a bottom sheet. |
| Tablet | 720 to 1024px | The sidebar rail and the activity rail appear. The sidebar preference appears with them. Omnisearch is still a single list, and a dossier is still an overlay. Settings is still a sheet. |
| Desktop | 1024 to 1280px | The sidebar is expanded and permanent. Omnisearch becomes two panes, so a dossier is a pane rather than an overlay. Settings becomes an anchored menu instead of a sheet. |
| Large | 1280 to 1920px | Same as Desktop. Content stops growing; margins take the extra width. |

Two stops carry nearly all the behavior:

- **720** is where the rails arrive. In code this is the `tablet:` variant, so a
  rule written as `hidden tablet:block` is a 720 rule.
- **1024** is where overlays become panes and the sheet becomes a menu. This is
  the stop that changes navigation shape rather than just density.

Below 720 every capture should be reachable one-handed: the drawer opens from
the top bar, and tap targets in sheets are 44px.

## What is enforced

No visual baseline suite runs today. The macOS screenshot baselines and the
breakpoint audit specs were deleted in #2053 because CI never ran them. A new
baseline suite needs a CI job and Linux baselines before it lands.
