# Native legal URL configuration

The founder requested configurable Terms and Privacy URLs on October 17, 2026.
The current website pages are defaults, pending app-policy approval. Native legal
links remain hidden by default. This change enables no rollout.

The earlier gate was an empty `CuadraoLegalURLs.published` value. There was no
separate named legal flag. The same owner now reads these public native build
settings through `Config/Info.plist`:

| Setting | Default |
| --- | --- |
| `ARGUS_CUADRAO_LEGAL_LINKS_ENABLED` | `false` |
| `ARGUS_CUADRAO_TERMS_URL` | `https://cuadrao.ai/terminos` |
| `ARGUS_CUADRAO_PRIVACY_URL` | `https://cuadrao.ai/privacidad` |

`Development.xcconfig` owns the defaults. `Local.xcconfig.example` documents the
same knobs. The existing ignored native local configuration was copied into the
isolated worktree for simulator testing, without changing its source. Backend and
web environment files were not created or changed.

All existing legal surfaces continue reading `CuadraoLegalURLs`. Disabled means
an empty owner even when URL settings are present. Enabled requires a valid HTTPS
URL for each displayed link. Missing or invalid settings hide their corresponding
links. Signup requires both documents and renders no legal content or space when
either is missing. Data-deletion URL publication is unchanged.

Connected signup and the reachable design preview use one shared acceptance
view. The Spanish sentence is “Al continuar, aceptas los Términos y la Política de
privacidad.” The English sentence is “By continuing, you agree to the Terms and
Privacy Policy.” Each document name is an inline link. There is no checkbox.
Preview legal buttons now use these real links rather than preview alerts.

The narrow overlap with PR #1170 at
`365c2fc21d65445a8898a90cf80d1abc2ccd365b` is the two Debug single-document
arguments in `CuadraoLegalURLs`, preview signup visibility and partial-document UI
coverage. Preserve that behavior when reconciling #1170. This PR owns the shared
acceptance view and configurable URL owner. Toast, profile and scan work remain
outside this change.

Integration base is `02502122aae107bc71ff123c7fb8060dc88f93ab`.

## Verification

- Offline `python3 ios/DesignPreviewTests/run_cuadrao_legal_urls.py` passed in
  Debug and Release. It checks the gate, configured destinations, missing/partial
  settings, invalid URLs and Release exclusion of Debug test arguments.
- Baseline signup screenshot test passed 1/1 on iPhone 18 Pro, iOS 27.0.
  `before-signup-es.png` shows the old sentence and separate legal links.
- Final focused simulator suite passed 6/6, 0 failures and 0 skipped. Both
  signup links open Safari. The tests cover guest Profile, hidden signup in both
  appearances, both single-document states in connected and preview signup, and
  the exact Spanish and English linked sentence. The result summary and signup
  screenshots are retained beside the baseline image.
- Actual built app Info.plist readback confirms the legal gate is `false` and
  the two public default URLs match the table above.
- Integration refresh still reads `02502122aae107bc71ff123c7fb8060dc88f93ab`.
  No reconciliation merge is needed. Modularity budget and diff checks pass.
- This is native local Xcode evidence. It is not hosted or physical-phone proof.
  Independent final-head review remains the coordinator's gate.

Simulator results establish native rendering only. No hosted signup, physical
phone, TestFlight, production or paid-provider action was performed.
