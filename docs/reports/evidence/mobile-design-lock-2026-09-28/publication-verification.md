# Publication verification

September 28, 2026. Documentation/reference publication, not native acceptance.

- Branch: `codex/native-interface-decision`.
- Pre-publication reference head: `57f36d5f45d36c2073e84a98b32cb33cfaad6172`.
- Publication commit: `8fe81659`.
- Fetched integration: `3b9313f3dcf80e3ff9eddfcce8818a829a081225`.
- One-way reconciliation: `018d62ae4d9604413ea036fd593fd92f570cc240`.
- Integration changes since the common ancestor affect research/cache/runtime
  logging and two reports. No shared runtime owner with this docs/reference diff;
  the final combined tree passed the modularity budget.

Verification on the reconciled tree:

- `poetry run python scripts/check_docs_links.py --base origin/codex/private-alpha-next`: 10 changed Markdown documents, passed before this publication note.
- `python3 scripts/check_modularity_budget.py`: no violations.
- Lane-planning contract validator: passed.
- `git diff --check origin/codex/private-alpha-next...HEAD`: passed.
- `poetry run pytest tests/test_private_alpha_release_docs.py -q --no-cov`: 22 passed.
- Frozen archive ZIP CRC: passed. SHA-256 matched the committed checksum.
- All 304 per-file manifest entries matched the archive's bytes.
- Extracted archive in an isolated temporary directory and ran its Node test
  files: 288 passed, zero failed/cancelled/skipped. The archive was not changed.

The Python preflight `import scipy.linalg` fails loading `_spropack` in this
checkout's existing Python 3.10 environment. No full backend-suite pass is
claimed and no shared dependency environment was repaired. Repository CI chooses
heavy checks because DESIGN.md lives outside `docs/`; do not label this diff
docs-only under that classifier even though no production runtime changes.

Browser captures remain the previously recorded design-baseline evidence and
were not recaptured for prose-only publication. The archive hash owns those
bytes; the Git head is not being substituted as a new browser proof. No model
calls, hosted settings, migrations, bank access, emails or simulator runs here.

Subsequent publication commits alter documentation only. Revalidate links and
whitespace at the final PR head; the unchanged archive retains its test evidence.
No terminal review/CI or release-readiness claim is made by this note.
