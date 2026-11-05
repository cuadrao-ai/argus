# Hunk classification contract (read-only task)

Goal: for each assigned file, classify every hunk of `git diff 5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37 HEAD -- <file>` into one of:

- **SEAM**: an opt-in parameter, protocol, extracted component or value that lets connected data feed the same Preview view. Test: the Preview canvas, called with its defaults/fixtures, renders byte-for-byte the same view tree, copy, spacing, colors, fonts, ids, animations and behavior as at the checkpoint. An extraction (code moved from a canvas into a `*Presentation.swift` / `*Layout.swift` / `*Display.swift` file) is a SEAM only if the moved code is unchanged in rendering; list each rendering difference you find inside the extracted copy as its own DRIFT item.
- **FIX**: a real defect fix the connected app needs (crash, data bug, perf fix that does not change rendering, accessibility-size fix that the Preview itself needed). Name the defect.
- **DRIFT**: changes the Preview look, behavior or copy without necessity: restyled, moved, reworded, deleted detail, changed accessibility identifier, changed layout container (LazyVStack to VStack), changed default parameter, dropped fixture detail, hidden control. Spanish is the approved wording: if the Spanish string changed, it is DRIFT even if English looks fine.
- **NEW**: an added file. For each NEW file also say which checkpoint code it was extracted from (file and line range), and whether the extracted rendering is unchanged (then SEAM) or changed (list DRIFT items).

Where to look:
- Checkpoint tree: `git show 5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37:<path>` or a read-only worktree of that commit
- Candidate tree: the branch under review
- Per-file diffs pre-split by `hunk_inventory.py` into `<outdir>/<path with / replaced by __>.diff`
- To know which seams the connected hosts use, grep the candidate tree's Connected/, Accounts/, Plan/, Search/, Household/, Auth/ directories for the symbol.
- Commit messages for the reason a hunk exists: `git log --oneline -L<start>,<end>:<file> 5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37..HEAD` or `git log -S'<symbol>'`.

Do NOT edit any file in any worktree. Do NOT run builds or simulators. Write only your output file.

Output file format (Markdown), one section per file in the order given, then a summary table:

```
## <path>
Base lines: N. Status: M|A.

### Hunk <n>: <@@ header> (<+a/-b>)
Class: SEAM | FIX | DRIFT | NEW
Used by: <connected caller file:line, or "none found">
Reason: <one or two sentences>
Restore: <for DRIFT only: exactly what the checkpoint had and what to put back; quote the Spanish string when copy changed>
```

Summary table at the end: `| file | SEAM | FIX | DRIFT | NEW |` with counts, then a bullet list "Highest-impact DRIFT" (max 10) ordered by what a user would notice.

Be precise and literal. Quote identifiers and strings. If a hunk mixes classes, split it into sub-items (Hunk 3a, 3b) each with its own class. If you are unsure, say UNSURE with both candidate classes and why.
