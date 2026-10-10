---
description: Coding standards — Python loguru/types/Pydantic, TypeScript zod/react-hook-form, mock data patterns.
globs: ["src/**/*.py", "web/**/*.ts", "web/**/*.tsx"]
---

# Coding Standards Rule

## Backend (Python)

1. Use `loguru` for all logging. Prohibit standard `logging` module and `print()` calls.
2. 100% type hint coverage on all function signatures.
3. 90 character line limit (ruff enforced).
4. Use Pydantic `BaseModel` for data crossing boundaries (API schemas).
5. Use `pydantic-settings` for configuration (never raw `os.environ`).
6. Modern Python: `str | None` not `Optional[str]`, `list[str]` not `List[str]`.

## Frontend (TypeScript/React)

7. 100% type coverage: Use explicit types on props, state, and function returns (no `any`).
8. Form validation: Use `zod` schema + `react-hook-form` for all user input.
9. API types: Mirror backend Pydantic schemas in TypeScript interfaces (e.g., `BacktestRequest` in both).
10. Client-side errors: Handle with React Query error boundaries + user-friendly UI messages (no console errors).
11. Mock data: Use existing frontend fixtures and mocked API clients in tests. Follow the operating reference for fast Dev Mode. The old `web/lib/mockData.ts` and `NEXT_PUBLIC_MOCK_API` notes are historical, not a current module or toggle.

## Shared Standards

12. **API Contract Clarity**: Pydantic schemas (`src/argus/api/schemas.py`) ↔ TypeScript types (`web/lib/api.ts`) must match exactly.
13. **No magic strings**: Use constants for API endpoints, feature flags, error codes (centralize in `web/lib/constants.ts`).
14. **Immutability patterns**: In backend, use `frozen=True` on Pydantic models when appropriate. In frontend, use `const` + React hooks (no mutation).

---

See: `.agent/skills/coding-standards/SKILL.md` for Python details, `.agent/skills/monorepo-patterns/SKILL.md` for sync patterns, `.agent/skills/mock-data-patterns/SKILL.md` for Faker usage.

## User-Facing Copy Punctuation

- Never use the em dash (—) in user-facing copy, in any language. Use a
  comma, colon, period, or the word that fits. Founder-locked 2026-08-04.
