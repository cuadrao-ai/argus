import { readdirSync, readFileSync, realpathSync } from "node:fs";
import { afterEach, mock } from "bun:test";
import { plugin } from "bun";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

// Bun's test runner does not compile CSS modules, so an import would be {}.
plugin({
  name: "css-modules",
  setup(build) {
    build.onLoad({ filter: /\.module\.css$/ }, async ({ path }) => {
      const css = await Bun.file(path).text();
      const names = [...css.matchAll(/(?:^|[\s,{])\.([A-Za-z_][\w-]*)/gm)].map((match) => match[1]);
      const fields = [...new Set(names)].map((name) => `${JSON.stringify(name)}:${JSON.stringify(name)}`).join(",");
      return { contents: `export default {${fields}};`, loader: "js" };
    });
  },
});

// A partial `mock.module` becomes the module's first evaluation when nothing
// has imported it yet, so every export the factory omits disappears. The
// replacement then stays in place for later files. `require` cannot load these
// modules, so import the mocked targets once before any file runs and keep a
// value copy. Put that copy back when the next test file is resolved. The copy
// has to be taken before the mock, because the live record changes underneath.
const applyModuleMock = mock.module.bind(mock);
const realByPath = new Map<string, Record<string, unknown>>();
const mockedPaths = new Set<string>();

function callerDir(): string {
  const frames = new Error().stack?.split("\n") ?? [];
  for (const frame of frames) {
    const match = frame.match(/\((.*):\d+:\d+\)$/) ?? frame.match(/at (.*):\d+:\d+$/);
    const raw = match?.[1];
    if (!raw || raw.includes("/setup.ts")) continue;
    const path = raw.startsWith("file://") ? raw.slice("file://".length) : raw;
    if (!path.startsWith("/")) continue;
    return path.slice(0, path.lastIndexOf("/"));
  }
  return import.meta.dir;
}

function resolvedPath(specifier: string, fromDir: string): string | null {
  try {
    return realpathSync(Bun.resolveSync(specifier, fromDir));
  } catch {
    return null;
  }
}

function copyExports(loaded: Record<string, unknown>): Record<string, unknown> {
  const copy: Record<string, unknown> = {};
  for (const key of Object.getOwnPropertyNames(loaded)) copy[key] = loaded[key];
  return copy;
}

function restoreRealExports(): void {
  for (const path of mockedPaths) {
    const real = realByPath.get(path);
    if (!real) continue;
    applyModuleMock(path, () => real);
  }
  mockedPaths.clear();
}

mock.module = ((specifier: string, factory: () => Record<string, unknown>) => {
  const path = resolvedPath(specifier, callerDir());
  if (path) mockedPaths.add(path);
  return applyModuleMock(specifier, factory);
}) as typeof mock.module;

plugin({
  name: "test-file-boundary",
  setup(build) {
    build.onResolve({ filter: /\.test\.tsx?$/ }, () => {
      restoreRealExports();
    });
  },
});

async function preloadMockTargets(): Promise<void> {
  const jobs: Array<{ specifier: string; dir: string }> = [];
  const seen = new Set<string>();
  const pending = [import.meta.dir];
  while (pending.length > 0) {
    const dir = pending.pop();
    if (!dir) break;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        pending.push(path);
        continue;
      }
      if (entry.name === "setup.ts" || !/\.tsx?$/.test(entry.name)) continue;
      const source = readFileSync(path, "utf8");
      for (const match of source.matchAll(/mock\.module\(\s*(['"])([^'"]+)\1/g)) {
        const key = `${dir}\0${match[2]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        jobs.push({ specifier: match[2], dir });
      }
    }
  }
  for (const job of jobs) {
    const path = resolvedPath(job.specifier, job.dir);
    if (!path || realByPath.has(path)) continue;
    try {
      realByPath.set(path, copyExports(await import(path)));
    } catch {
      realByPath.delete(path);
    }
  }
}

/**
 * Preloaded by bunfig before every test file, so no file's global state is
 * what the next file starts from, whatever order `--randomize` picks.
 */

// `CUADRAO_API_BASE_URL` is computed once, at first import, from whether a
// `window` exists. Whichever file imported it first decided the answer for
// every later file, so a happy-dom file reaching it first made the base URL
// `http://localhost:8000` for the whole run. Importing it here, with no DOM,
// pins the server-side value `http://127.0.0.1:8000`.
await import("../lib/argus-api-transport");

// `react-dom/client` decides once, at first import, whether the platform can
// use the `input` event. With no `window` at that moment it decides no for the
// whole run, and `onChange` never fires on typing. Files import it statically
// (`receipt-activity`) or after registering their own DOM, so whichever came
// first under `--randomize` decided for the rest. Importing it here against a
// DOM, then removing the DOM, makes the answer the same for every order.
GlobalRegistrator.register({ url: "http://localhost" });
await import("react-dom/client");
await GlobalRegistrator.unregister();
await preloadMockTargets();

type Resettable = Record<string, unknown>;

/**
 * Exports of a module only if some file already loaded it. Importing it here
 * instead would evaluate it before any DOM is registered, and modules such as
 * the overlay stack pick their behaviour from that moment.
 */
function loadedExports(specifier: string): Resettable | null {
  try {
    const entry = require.cache[require.resolve(specifier)];
    return (entry?.exports as Resettable | undefined) ?? null;
  } catch {
    return null;
  }
}

// Module-level state with a test seam. The overlay stack holds open layers and
// a `listening` flag, and the history module holds unspent entries and pending
// traversals. A finished sign-out leaves its flag set, and the chosen Business
// grant stays selected. A file that sets one without clearing it leaves it for
// the next file.
afterEach(() => {
  const reset = (specifier: string, name: string) => {
    const seam = loadedExports(specifier)?.[name];
    if (typeof seam === "function") seam();
  };
  reset("../components/layout/overlayStack", "resetOverlayStack");
  reset("../lib/overlay-history", "resetOverlayEntries");
  reset("../lib/logout-flow", "resetLeavingSession");
  const clearGrant = loadedExports("../lib/business-grant")?.setChosenGrant;
  if (typeof clearGrant === "function") clearGrant(null);
});
