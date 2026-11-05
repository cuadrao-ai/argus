PR864 independent local live verification

Source head: 9419001712dc9f070741909312982f19d1e08e72; original worktree remained clean.

Swift 4/4 passed, zero skips, zero failures, 33.248s. Full output in swift-live.log.
- LiveFinancialAccountTests.testLocalDurableAccountsThroughProductionClient
- LiveSessionTests.testLiveConcurrentRefreshAfterExpiryMargin
- LiveSessionTests.testLiveInvalidLoginAndConfirmationRequiredSignup
- LiveSessionTests.testLiveRegisteredRelaunchRevocationAndAccountSwitch

Used actual production Swift SDK/transport, real local API/Auth/Postgres, macOS Keychain, synthetic users. Independent package copy adapted only fixture allowed ports from58400/58401 to60341/60331. No product source edits. Independent scratch/cache package build passed in11.03s.

Python tests/test_profile_apple_identity_postgres.py: 5/5 passed, zero skips, 2.01s, including [removed obsolete setting]=1 signed local Auth owner-isolation test. PYTHONPATH included frozen src and web contract package. Initial non-escalated invocation hit local-network sandbox prohibition; no test rows were created. First harness also lacked web package path; fixed only harness before successful run.

Cleanup verified by harness: original owned Auth container ID and complete Config restored exactly; health endpoint returned200; all test-owned users deleted and complete initial auth.users ID set unchanged; owned API60341 terminated; temporary credential fixture deleted. No shared project config files changed, no volume reset, no simulator, hosted/provider/model or root .env access. Original Auth settings JWT3600 and auto-confirm true restored after temporarily running JWT60 and confirmation required; SMTP remained local inbucket.

Automatic approval review rejected saving full Docker inspect JSON because it could retain secret environment values. Safer approach inspected only nonsecret metadata and retained the original stopped Auth container for restoration. Auth environment values remained in process memory; no full configuration secret file was written.
