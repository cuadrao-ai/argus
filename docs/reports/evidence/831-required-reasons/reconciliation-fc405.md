# PR 849 reconciliation after the lock observer fix

This October 5, 2026 record extends [the currency reconciliation](reconciliation-2b.md).

- Previous published PR head is `3c6c95b9a9ea6ee1a5c7b12d3ab96f45ce8ba6c3`.
- Fetched integration is `fc4057c8789d3e3504fcb0e980344d6bf51e66c0`.
- The normal reconciliation merge is `5cdb8ae6bbf354c23c380a42e65b49172d229595`.
- This evidence commit changes no implementation. The handoff records the final published head.

PR 868 changes only a Postgres lock-observer test and its evidence. The entire `ios` tree is byte-identical to the previous published head. Existing manifest audit inputs and evidence files are also byte-identical, excluding this new reconciliation record. The preceding required-reason API inventory, dependency, configuration, and packaged-byte comparisons therefore remain valid. This landing changes no production code or manifest input.

Seven manifest validators passed again, with zero failures and zero skips. The combined tree's modularity budget has zero violations. `git diff --check` passes. The manifest implementation's stable patch ID remains `54fcbcff41ecafce9b9ad0fed4a9733f8a8a8d29`.

The retained unsigned Release app remains a baseline packaging artifact only. This pass ran no fresh build, simulator, database, or provider operation. No resource lease was used. Phone, signed archive, legal approval, and external acceptance gates remain open. Independent final context review, exact-head CI, and guarded landing remain with the release captain.
