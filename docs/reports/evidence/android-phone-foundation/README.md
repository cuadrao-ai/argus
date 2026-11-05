# Android foundation device evidence

Initial source commit: `8fe35fd32abf0c27ffbc08312db082a4478ba964`.
App main tree: `a5618ee4b264947e4d0f27741dee1e5354522d8e`.
English captures and logs were refreshed after the draft-recreation fix at
`2df05cd88725b1d00160bdc111c651ed650a0e03` (app main tree
`b54c201a96b643eb10330d6632eb864f5bcf0d7b`). Both full 9-test suites pass,
including the added draft-after-recreation assertion. Spanish layout and manual
appearance/IME evidence remain valid: only the composer state holder changed;
rendering, strings, theme, navigation and preference storage are unchanged.

All captures are direct unedited emulator screenshots of the disconnected sample.
Only fictional fixtures and a synthetic draft are present.

| Folder | Phone | Locale | Font scale | Coverage |
| --- | --- | --- | --- | --- |
| `en-small` | Pixel 4 / 360dp | en-US | 1.0 | All five destinations |
| `en-large` | Pixel 7 Pro / 411dp | en-US | 1.0 | All five destinations |
| `es-small` | Pixel 4 / 360dp | es-419 | 1.3 | Home, Argus, Plan, Dark, chat registration |
| `es-large` | Pixel 7 Pro / 411dp | es-419 | 1.3 | Home, Argus, Plan, Dark, chat registration |
| `manual-small` | Pixel 4 / 360dp | en-US | 1.0 | Dark cold restart, keyboard/Back |

Each `*-instrumentation.txt` records 9 passing tests; `verification.json`
records the matrix. `manual-small/checks.json` records manual assertions and
`appearance-after-restart.xml` is the sample app's sole preference.

## Representative captures

![Small phone Home](en-small/tab_home.png)
![Large phone Argus](en-large/tab_argus.png)
![Spanish enlarged Plan](es-small/tab_plan.png)
![Spanish Dark appearance](es-large/appearance_dark.png)
![Chat registration boundary](es-small/registration_chat.png)
![Cold restart retains Dark](manual-small/cold-restart-dark.png)
![Keyboard hides bottom navigation](manual-small/composer-keyboard.png)

## Limits

API 36 ARM64 emulators only. No physical-device, TalkBack, older-API,
production-auth or finance-runtime claim. See the [acceptance report](../../android-phone-foundation.md).
