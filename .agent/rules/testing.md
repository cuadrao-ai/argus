---
description: TDD-first, 63% coverage target, pytest practices, mock data integration, frontend testing.
globs:
  ["tests/**/*.py", "web/__tests__/**/*.test.ts", "web/__tests__/**/*.test.tsx"]
---

# Testing Rule

## Backend (Python)

1. **TDD-first**: Write a failing test before fixing any bug.
2. **Coverage target**: 63% minimum. Focus on analysis logic (src/argus/analysis/).
3. Use plain `assert` and `pytest.approx()` for floats.
4. Name tests descriptively: `test_<behavior>`.
5. Use `conftest.py` for shared fixtures.
6. Call `warmup_jit()` before any Numba performance tests.
7. **Test with Faker**: In `tests/`, use `from faker import Faker; fake = Faker()` to generate test data (realistic symbols, dates, prices).

## Frontend (TypeScript)

8. **Unit tests**: Use Vitest (via Bun) for component testing. Test user interactions, not implementation details.
9. **Mock API in tests**: Use the existing Vitest fixtures and mocked API clients. Make no real API calls. `NEXT_PUBLIC_MOCK_API` is a historical note, not a current test toggle.
10. **Form validation**: Test with zod schemas + react-hook-form; verify error messages render correctly.
11. **Integration tests**: Test critical workflows end-to-end:
    - Login flow (auth + session persistence)
    - Strategy creation (form → API → list update)
    - Backtest execution (submit → loading → results display)

## Shared

12. **API Contract Testing**: Backend tests must cover all request/response shapes defined in `docs/API_CONTRACT.md`. Frontend tests must consume those same types.
13. **No hardcoded test data**: Use Faker in Python and existing frontend test fixtures for realistic data. The old `web/lib/mockData.ts` pointer is historical; no current module exists at that path.
14. **Rate limit tests**: Include tests for all 4 tiers (free, pro, pro+, enterprise) + quota resets.

---

See: `.agent/skills/testing-patterns/SKILL.md` for pytest details, `.agent/skills/mock-data-patterns/SKILL.md` for Faker patterns.
