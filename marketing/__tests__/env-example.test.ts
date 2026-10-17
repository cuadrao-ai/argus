import { afterEach, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { checkExample } from "../scripts/check-env-example";

const directories: string[] = [];

afterEach(() => {
  for (const directory of directories.splice(0)) rmSync(directory, { recursive: true, force: true });
});

function fixture(files: Record<string, string>) {
  const root = mkdtempSync(join(tmpdir(), "marketing-env-"));
  directories.push(root);
  for (const [path, content] of Object.entries(files)) {
    const target = join(root, path);
    mkdirSync(join(target, ".."), { recursive: true });
    writeFileSync(target, content);
  }
  return root;
}

test("reports missing dot, literal bracket, destructured and aliased names across wrappers", () => {
  const root = fixture({
    ".env.example": "DIRECT=\n",
    "app.ts": 'import { config } from "./config"; const environment = process.env; config(environment); environment.DIRECT;',
    "config.ts": 'export function config(settings) { const alias = settings; const { DESTRUCTURED: renamed } = alias; return [alias["BRACKET"], alias.DIRECT, renamed]; }',
  });
  const result = checkExample(root);
  expect(result.names).toEqual(["BRACKET", "DESTRUCTURED", "DIRECT"]);
  expect(result.errors).toEqual([".env.example is missing BRACKET", ".env.example is missing DESTRUCTURED"]);
});

test("follows default env parameters, process aliases, casts, and imported env", () => {
  const root = fixture({
    ".env.example": "DEFAULTED=\nIMPORTED=\nPROCESS_ALIAS=\n",
    "runtime.ts": 'import { env as imported } from "node:process"; const p = process; const vars = p["env"]; function config(settings = process.env) { return (settings as Record<string, string>).DEFAULTED; } vars.PROCESS_ALIAS; imported.IMPORTED;',
  });
  expect(checkExample(root)).toEqual({ names: ["DEFAULTED", "IMPORTED", "PROCESS_ALIAS"], errors: [] });
});

test("follows environment aliases exported between runtime modules", () => {
  const root = fixture({
    ".env.example": "EXPORTED=\nGLOBAL=\n",
    "env.ts": "export const settings = process.env;",
    "runtime.ts": 'import { settings as current } from "./env"; current.EXPORTED; globalThis.process.env.GLOBAL;',
  });
  expect(checkExample(root)).toEqual({ names: ["EXPORTED", "GLOBAL"], errors: [] });
});

test("covers CommonJS process imports and global process access", () => {
  const root = fixture({
    ".env.example": "CJS=\nGLOBAL=\nREQUIRED=\n",
    "runtime.cjs": 'const p = require("node:process"); const { env: vars } = require("process"); p.env.CJS; vars["REQUIRED"]; global.process.env.GLOBAL;',
  });
  expect(checkExample(root)).toEqual({ names: ["CJS", "GLOBAL", "REQUIRED"], errors: [] });
});

test.each([
  'process.env[key]',
  'const vars = process.env; vars[key]',
  'function config(settings = process.env) { return settings[key]; }',
  'const { [key]: value } = process.env;',
  'const { ...rest } = process.env;',
  'Object.keys(process.env)',
  'const copy = { ...process.env };',
  'function leak() { return process.env; }',
  'const p = process; p[key];',
])("rejects unsupported runtime reads instead of skipping them: %s", (source) => {
  const root = fixture({ ".env.example": "", "runtime.ts": source });
  expect(checkExample(root).errors.some((error) => error.includes("Unsupported"))).toBe(true);
});

test("ignores fixture/test reads but covers scripts and package configuration", () => {
  const root = fixture({
    ".env.example": "CI=\nOPERATOR=\n",
    "playwright.config.ts": "process.env.CI",
    "scripts/operator.mjs": "process.env.OPERATOR",
    "e2e/fixture.ts": "process.env.FIXTURE_ONLY",
    "__tests__/unit.ts": "process.env.TEST_ONLY",
    "scripts/unit.test.mjs": "process.env.TEST_ONLY",
    "node_modules/package/index.js": "process.env.DEPENDENCY",
    ".next/server.js": "process.env.GENERATED",
    "notes.md": "process.env.DOCUMENTATION",
  });
  expect(checkExample(root)).toEqual({ names: ["CI", "OPERATOR"], errors: [] });
});

test("does not mistake a shadowed process or strings/comments for environment reads", () => {
  const root = fixture({
    ".env.example": "",
    "runtime.ts": 'const process = { env: { LOCAL: "value" } }; process.env.LOCAL; const example = "process.env.STRING"; // process.env.COMMENT',
  });
  expect(checkExample(root)).toEqual({ names: [], errors: [] });
});

test("command exits with failure when a runtime name is absent", () => {
  const root = fixture({ ".env.example": "", "runtime.ts": "process.env.MISSING" });
  const result = Bun.spawnSync(["bun", join(import.meta.dir, "../scripts/check-env-example.ts"), root]);
  expect(result.exitCode).toBe(1);
  expect(result.stderr.toString()).toContain(".env.example is missing MISSING");
});
