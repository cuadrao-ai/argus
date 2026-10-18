import { afterEach } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

/**
 * Preloaded by bunfig before every test file, so no file's global state is
 * what the next file starts from, whatever order `--randomize` picks.
 */

// `ARGUS_API_BASE_URL` is computed once, at first import, from whether a
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
// traversals; a file that opens one without closing it leaves it open for the
// next file.
afterEach(() => {
  const reset = (specifier: string, name: string) => {
    const seam = loadedExports(specifier)?.[name];
    if (typeof seam === "function") seam();
  };
  reset("../components/layout/overlayStack", "resetOverlayStack");
  reset("../lib/overlay-history", "resetOverlayEntries");
  reset("../lib/age-confirmation", "resetAgeConfirmationForTests");
});
