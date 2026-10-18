import { afterEach, describe, expect, spyOn, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import * as guestCaptcha from "../lib/guest-captcha";
import { applyGuestBootstrapError } from "../lib/guest-entry-error";

const globalRestores: Array<() => void> = [];

function stubGlobal(name: "window" | "document", value: unknown) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, {
    configurable: true,
    enumerable: true,
    writable: true,
    value,
  });
  const restore = () => {
    if (previous) {
      Object.defineProperty(globalThis, name, previous);
      return;
    }
    Reflect.deleteProperty(globalThis, name);
  };
  globalRestores.push(restore);
  return restore;
}

function restoreStubbedGlobals() {
  while (globalRestores.length > 0) {
    globalRestores.pop()?.();
  }
}

afterEach(() => {
  restoreStubbedGlobals();
});

const root = join(import.meta.dir, "..");

type AcquireTurnstileChallenge = (input: {
  turnstile: ReturnType<typeof challengeHarness>["turnstile"];
  shell: ReturnType<typeof challengeHarness>["shell"];
  siteKey: string;
  timeoutMs: number;
  interactiveTimeoutMs: number;
  theme: "light" | "dark";
  signal?: AbortSignal;
}) => Promise<string>;

function challengeUnderTest(): AcquireTurnstileChallenge {
  const acquire = (
    guestCaptcha as typeof guestCaptcha & {
      acquireTurnstileChallenge?: AcquireTurnstileChallenge;
    }
  ).acquireTurnstileChallenge;
  expect(typeof acquire).toBe("function");
  return acquire as AcquireTurnstileChallenge;
}

function challengeHarness() {
  let destroyCalls = 0;
  let removeCalls = 0;
  let revealCalls = 0;
  let renderedTheme: "auto" | "light" | "dark" | undefined;
  let callbacks:
    | {
        callback: (token: string) => void;
        "error-callback": (code?: string) => boolean;
        "expired-callback": () => void;
        "before-interactive-callback": () => void;
      }
    | undefined;

  const shell = {
    container: {} as HTMLElement,
    destroy() {
      destroyCalls += 1;
    },
    reveal() {
      revealCalls += 1;
    },
  };
  const turnstile = {
    render(
      _container: HTMLElement,
      options: {
        theme: "auto" | "light" | "dark";
        callback: (token: string) => void;
        "error-callback": (code?: string) => boolean;
        "expired-callback": () => void;
        "before-interactive-callback": () => void;
      },
    ) {
      callbacks = options;
      renderedTheme = options.theme;
      return "widget-1";
    },
    remove(widgetId: string) {
      expect(widgetId).toBe("widget-1");
      removeCalls += 1;
    },
  };

  return {
    shell,
    turnstile,
    get callbacks() {
      return callbacks;
    },
    get destroyCalls() {
      return destroyCalls;
    },
    get removeCalls() {
      return removeCalls;
    },
    get revealCalls() {
      return revealCalls;
    },
    get renderedTheme() {
      return renderedTheme;
    },
  };
}

describe("shared CAPTCHA acquisition UX", () => {
  test.each(
    (["success", "error", "expired"] as const).flatMap((outcome) =>
      [true, false].map((synchronous) => [outcome, synchronous] as const),
    ),
  )(
    "keeps the provider container alive after %s (synchronous render: %s)",
    async (outcome, synchronous) => {
      const harness = challengeHarness();
      let providerSawLiveContainer = false;
      const render = harness.turnstile.render;
      harness.turnstile.render = (container, options) => {
        expect(options).toMatchObject({
          retry: "never",
          "refresh-expired": "never",
          "refresh-timeout": "never",
        });
        const id = render(container, options);
        const deliver = () => {
          if (outcome === "success") options.callback("verified-token");
          else if (outcome === "error") options["error-callback"]();
          else options["expired-callback"]();
          providerSawLiveContainer =
            harness.destroyCalls === 0 && harness.removeCalls === 0;
          options.callback("late-token");
          options["error-callback"]();
        };
        if (synchronous) deliver();
        else setTimeout(deliver, 0);
        return id;
      };
      const result = await challengeUnderTest()({
        turnstile: harness.turnstile,
        shell: harness.shell,
        siteKey: "test-site-key",
        timeoutMs: 100,
        interactiveTimeoutMs: 100,
        theme: "light",
      }).catch((error: unknown) => error);
      expect(providerSawLiveContainer).toBe(true);
      if (outcome === "success") expect(result).toBe("verified-token");
      else expect(result).toMatchObject({ code: "captcha_unavailable" });
      expect(harness.removeCalls).toBe(1);
      expect(harness.destroyCalls).toBe(1);
    },
  );

  test("times out a Turnstile widget that never settles and ignores a late callback", async () => {
    const harness = challengeHarness();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 5,
      interactiveTimeoutMs: 100,
      theme: "light",
    });

    const error = await pending.catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(Error);
    expect((error as Error & { code?: string }).code).toBe(
      "captcha_unavailable",
    );
    expect(harness.removeCalls).toBe(1);
    expect(harness.destroyCalls).toBe(1);

    harness.callbacks?.callback("too-late");
    expect(harness.removeCalls).toBe(1);
    expect(harness.destroyCalls).toBe(1);
  });

  test("allows an invisible check to resolve before the deadline", async () => {
    const harness = challengeHarness();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 100,
      interactiveTimeoutMs: 100,
      theme: "light",
    });

    setTimeout(() => harness.callbacks?.callback("verified-token"), 1);

    await expect(pending).resolves.toBe("verified-token");
    expect(harness.removeCalls).toBe(1);
    expect(harness.destroyCalls).toBe(1);
  });

  test("gives a revealed interactive challenge a fresh completion window", async () => {
    const harness = challengeHarness();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 10,
      interactiveTimeoutMs: 100,
      theme: "dark",
    });

    setTimeout(
      () => harness.callbacks?.["before-interactive-callback"]?.(),
      1,
    );
    setTimeout(() => harness.callbacks?.callback("interactive-token"), 30);

    await expect(pending).resolves.toBe("interactive-token");
    expect(harness.revealCalls).toBe(1);
    expect(harness.removeCalls).toBe(1);
    expect(harness.destroyCalls).toBe(1);
  });

  test("an abort in the tick after a token rejects instead of resolving", async () => {
    const harness = challengeHarness();
    const controller = new AbortController();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 1000,
      interactiveTimeoutMs: 1000,
      theme: "light",
      signal: controller.signal,
    });

    harness.callbacks?.callback("verified-token");
    controller.abort();
    const error = await pending.catch((caught: unknown) => caught);
    expect(error).toMatchObject({ name: "AbortError" });
    expect(harness.removeCalls).toBe(1);
    expect(harness.destroyCalls).toBe(1);
  });

  test("abort destroys a pending Turnstile shell before it can reveal", async () => {
    const harness = challengeHarness();
    const controller = new AbortController();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 1000,
      interactiveTimeoutMs: 1000,
      theme: "light",
      signal: controller.signal,
    });

    controller.abort();
    const error = await pending.catch((caught: unknown) => caught);
    expect(error).toMatchObject({ name: "AbortError" });
    expect(harness.removeCalls).toBe(1);
    expect(harness.destroyCalls).toBe(1);
    harness.callbacks?.["before-interactive-callback"]?.();
    harness.callbacks?.callback("too-late");
    expect(harness.revealCalls).toBe(0);
    expect(harness.destroyCalls).toBe(1);
  });

  test("passes the page's resolved theme to Turnstile", async () => {
    const harness = challengeHarness();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 100,
      interactiveTimeoutMs: 100,
      theme: "dark",
    });

    harness.callbacks?.callback("verified-token");

    await expect(pending).resolves.toBe("verified-token");
    expect(harness.renderedTheme).toBe("dark");
  });

  test("ships the interactive verification label in English and Spanish", () => {
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    expect(en.auth.captcha?.verifying).toBe("Verifying you’re not a bot…");
    expect(es.auth.captcha?.verifying).toBe(
      "Verificando que no eres un bot…",
    );
  });

  test("an unavailable acquisition plan throws captcha_unavailable", async () => {
    const originalNodeEnv = process.env.NODE_ENV;
    const originalLocalToken =
      process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
    const originalCuadraoSiteKey = process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
    const originalTurnstileSiteKey =
      process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
    const originalApiUrl = process.env.NEXT_PUBLIC_ARGUS_API_URL;
    process.env.NODE_ENV = "production";
    delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
    delete process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
    delete process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
    process.env.NEXT_PUBLIC_ARGUS_API_URL =
      "https://api.argus.example/api/v1";
    try {
      const error = await guestCaptcha
        .acquireGuestCaptchaToken()
        .catch((caught: unknown) => caught);
      expect(guestCaptcha.isCaptchaUnavailableError(error)).toBe(true);
      expect(guestCaptcha.guestEntryErrorKind(error)).toBe(
        "captcha_unavailable",
      );
    } finally {
      process.env.NODE_ENV = originalNodeEnv;
      if (originalLocalToken === undefined) {
        delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
      } else {
        process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN =
          originalLocalToken;
      }
      if (originalCuadraoSiteKey === undefined) {
        delete process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
      } else {
        process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY = originalCuadraoSiteKey;
      }
      if (originalTurnstileSiteKey === undefined) {
        delete process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
      } else {
        process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY =
          originalTurnstileSiteKey;
      }
      if (originalApiUrl === undefined) {
        delete process.env.NEXT_PUBLIC_ARGUS_API_URL;
      } else {
        process.env.NEXT_PUBLIC_ARGUS_API_URL = originalApiUrl;
      }
    }

    const captcha = readFileSync(join(root, "lib/guest-captcha.ts"), "utf-8");
    const unavailableBranch = captcha.slice(
      captcha.indexOf('if (plan.kind === "unavailable")'),
      captcha.indexOf("const deadline"),
    );
    expect(unavailableBranch).toContain("throw captchaUnavailableError()");
    expect(captcha).not.toContain(
      "Guest access requires a configured browser CAPTCHA before production exposure.",
    );
  });

  test("script-load and missing-turnstile failures classify as captcha_unavailable", async () => {
    const loadTurnstile = (
      guestCaptcha as typeof guestCaptcha & {
        loadTurnstile?: (timeoutMs: number) => Promise<unknown>;
      }
    ).loadTurnstile;
    expect(typeof loadTurnstile).toBe("function");
    const load = loadTurnstile as (timeoutMs: number) => Promise<unknown>;

    const classifyLoadFailure = async (trigger: "error" | "load") => {
      const listeners = new Map<string, () => void>();
      const script = {
        addEventListener(type: string, handler: () => void) {
          listeners.set(type, handler);
        },
        removeEventListener(type: string) {
          listeners.delete(type);
        },
        remove() {},
        id: "",
        src: "",
        async: false,
        defer: false,
      };
      stubGlobal("window", {
        turnstile: undefined,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      });
      stubGlobal("document", {
        getElementById: () => null,
        createElement: () => script,
        head: { appendChild() {} },
      });
      try {
        const pending = load(50);
        listeners.get(trigger)?.();
        const error = await pending.catch((caught: unknown) => caught);
        expect(guestCaptcha.isCaptchaUnavailableError(error), trigger).toBe(
          true,
        );
        expect(guestCaptcha.guestEntryErrorKind(error), trigger).toBe(
          "captcha_unavailable",
        );
      } finally {
        restoreStubbedGlobals();
      }
    };

    await classifyLoadFailure("error");
    await classifyLoadFailure("load");

    const captcha = readFileSync(join(root, "lib/guest-captcha.ts"), "utf-8");
    expect(captcha).not.toContain("Browser CAPTCHA could not start.");
    expect(captcha).not.toContain("Browser CAPTCHA could not load.");
  });

  test.each(["600010", "token-like-secret", "600010 extra"])("keeps only safe provider error codes: %s", async (providerCode) => {
    const warning = spyOn(console, "warn").mockImplementation(() => {});
    globalRestores.push(() => warning.mockRestore());
    const harness = challengeHarness();
    const pending = challengeUnderTest()({
      turnstile: harness.turnstile,
      shell: harness.shell,
      siteKey: "test-site-key",
      timeoutMs: 100,
      interactiveTimeoutMs: 100,
      theme: "light",
    });

    const returned = (
      harness.callbacks?.["error-callback"] as
        | ((code?: string) => boolean)
        | undefined
    )?.(providerCode);
    harness.callbacks?.["error-callback"]?.(providerCode);
    const error = await pending.catch((caught: unknown) => caught);
    expect(warning.mock.calls).toEqual(
      providerCode === "600010" ? [["turnstile_challenge_failed", providerCode]] : [],
    );

    expect((error as { turnstileCode?: string }).turnstileCode).toBe(
      providerCode === "600010" ? providerCode : undefined,
    );
    expect(returned).toBe(true);
    expect(error).toBeInstanceOf(Error);
    expect((error as Error & { code?: string }).code).toBe(
      "captcha_unavailable",
    );
    expect(guestCaptcha.guestEntryErrorKind(error)).toBe("captcha_unavailable");
  });

  test("maps coded Turnstile failures to captcha_unavailable and other errors to generic", () => {
    const coded = Object.assign(new Error("Browser CAPTCHA could not be verified."), {
      code: "captcha_unavailable",
    });
    expect(guestCaptcha.isCaptchaUnavailableError(coded)).toBe(true);
    expect(guestCaptcha.guestEntryErrorKind(coded)).toBe("captcha_unavailable");
    expect(guestCaptcha.guestEntryErrorKind(new Error("network"))).toBe(
      "generic",
    );
    expect(guestCaptcha.guestEntryErrorKind()).toBe("generic");
    expect(guestCaptcha.guestEntryErrorKind("captcha_unavailable")).toBe(
      "generic",
    );
  });

  test("captcha_unavailable clears the guest entry retry; other errors keep it", () => {
    const coded = Object.assign(new Error("Browser CAPTCHA could not be verified."), {
      code: "captcha_unavailable",
    });
    const captchaRetry = { current: { text: "retry me" } };
    expect(applyGuestBootstrapError(coded, captchaRetry)).toBe(
      "captcha_unavailable",
    );
    expect(captchaRetry.current).toBeNull();

    const genericRetry = { current: { text: "keep me" } };
    expect(applyGuestBootstrapError(new Error("network"), genericRetry)).toBe(
      "generic",
    );
    expect(genericRetry.current).toEqual({ text: "keep me" });
  });
});
