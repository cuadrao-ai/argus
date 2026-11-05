# Argus chart validation prototype

Standalone, synthetic rendering and interaction experiment. It does not connect
to Argus, calculate forecasts or balances, or add charts to product screens.

- [Spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-28-chart-validation-prototype.md)
- [Proposed fixture contract](CONTRACT.md)
- [Single fixture source](fixtures/series.json)
- [iPhone](ios/README.md), [Android](android/README.md), [web](web/README.md)
- [Evidence](../../docs/reports/evidence/chart-validation/README.md)

The historical series reuses Argus's dated portfolio-value semantics. Projection
and explicit missing-interval fields are proposed only. All values are synthetic;
each platform renders the same bytes. USD and DOP are never combined.

The card shows actual and projected lines, a selected date/value, and large
Previous / Next / Reset controls. Horizontal dragging selects a date; vertical
dragging leaves page scrolling available. Missing points remain selectable.
Touch release keeps selection, cancellation restores the pre-drag selection,
and changing scenario clears it. Locale/theme only change presentation.

Run the platform-independent contract checks from the repository root:

```sh
python3 -m unittest discover -s prototypes/chart-validation/scripts -p 'test_*.py' -v
```

Platform READMEs own build and device commands. Projects have separate app IDs,
build files and dependency locks. They neither import unmerged foundation shells
nor alter shared native/web build configuration. Keep local devices dedicated to
this prototype and record IDs before cleanup; native-auth devices are occupied.

Screenshots and performance are simulator/emulator/browser evidence. No physical
phone, older minimum-OS runtime, energy, thermal, or assistive-technology user
acceptance claim follows from those captures.
