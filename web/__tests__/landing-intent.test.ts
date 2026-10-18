import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  attributionPayload,
  authLoginPathFromSearch,
  CAMPAIGN_VALUE_FIELDS,
  captureLandingIntent,
  businessShellPath,
  currentChatPath,
  businessShellEntry,
  homeTarget,
  postAuthPath,
  signedInHomePath,
  hasCampaignAttribution,
  LANDING_INTENT_STORAGE_KEY,
  LANDING_STARTER_STORAGE_KEY,
  LANDING_STARTER_RUNTIME_FALLBACK_MS,
  landingStarterAppliedThisRuntime,
  landingStarterSurfaceEpoch,
  mergeFirstTouchLandingIntent,
  noteLandingStarterComposerMatch,
  parseLandingIntent,
  parseLandingStarter,
  pathWithSearch,
  prepareLandingStarterAuthHandoff,
  readLandingIntent,
  resetLandingStarterRuntime,
  sanitizeLandingPath,
  sanitizeLandingStarter,
  stripLandingStarterFromLocation,
  takeLandingStarterPrefill,
} from "../lib/landing-intent";

function installStorage() {
  const local = new Map<string, string>();
  const session = new Map<string, string>();
  const localStorage = {
    getItem: (key: string) => local.get(key) ?? null,
    setItem: (key: string, value: string) => {
      local.set(key, value);
    },
    removeItem: (key: string) => {
      local.delete(key);
    },
  };
  const sessionStorage = {
    getItem: (key: string) => session.get(key) ?? null,
    setItem: (key: string, value: string) => {
      session.set(key, value);
    },
    removeItem: (key: string) => {
      session.delete(key);
    },
  };
  const location = { search: "", pathname: "/", hash: "" };
  (globalThis as { window?: unknown }).window = {
    localStorage,
    sessionStorage,
    location,
    history: {
      replaceState: (_state: unknown, _title: string, url: string) => {
        const parsed = new URL(url, "https://argus.test");
        location.pathname = parsed.pathname;
        location.search = parsed.search;
        location.hash = parsed.hash;
      },
    },
  };
  return { local, session, location };
}

afterEach(() => {
  resetLandingStarterRuntime();
  delete (globalThis as { window?: unknown }).window;
});

describe("landing intent parsing", () => {
  test("keeps campaign fields and the starter whitelist", () => {
    expect(
      parseLandingIntent(
        "utm_source=ig&utm_medium=paid&utm_campaign=x&utm_term=meta-kw&utm_content=card-a&fbclid=abc.1&ref=stories&starter=backtest",
        "/",
      ),
    ).toEqual({
      utm_source: "ig",
      utm_medium: "paid",
      utm_campaign: "x",
      utm_term: "meta-kw",
      utm_content: "card-a",
      fbclid: "abc.1",
      ref: "stories",
      starter: "backtest",
      landing_path: "/",
    });
  });

  test("drops unknown starters and keeps decoded campaign values", () => {
    expect(
      parseLandingIntent(
        "starter=prompt-injection&utm_campaign=<script>&ref=ok%20space&utm_source=ig",
        "https://evil.example/chat",
      ),
    ).toEqual({
      utm_source: "ig",
      utm_campaign: "<script>",
      ref: "ok space",
    });
    expect(sanitizeLandingStarter("savings")).toBe("savings");
    expect(sanitizeLandingStarter("SAVINGS")).toBeUndefined();
    expect(sanitizeLandingStarter("hold")).toBeUndefined();
    expect(sanitizeLandingPath("/chat")).toBe("/chat");
    expect(sanitizeLandingPath("//evil")).toBeUndefined();
    expect(sanitizeLandingPath("/chat?x=1#y")).toBe("/chat");
  });

  test("keeps decoded campaign spaces without the starter token whitelist", () => {
    expect(
      parseLandingIntent("utm_campaign=fall+sale&utm_content=card%20a", "/chat"),
    ).toEqual({
      utm_campaign: "fall sale",
      utm_content: "card a",
      landing_path: "/chat",
    });
  });

  test("caps overlong tokens rather than storing the raw query", () => {
    const tooLong = `ig-${"a".repeat(400)}`;
    expect(parseLandingIntent(`utm_source=${tooLong}`).utm_source).toHaveLength(
      256,
    );
    expect(parseLandingIntent(`utm_term=${tooLong}`).utm_term).toHaveLength(256);
  });

  test("captures utm_term, carries it through the login bounce, and treats it as campaign", () => {
    installStorage();
    expect(parseLandingIntent("utm_term=meta-kw", "/")).toEqual({
      utm_term: "meta-kw",
      landing_path: "/",
    });
    expect(captureLandingIntent("utm_term=meta-kw", "/")).toEqual({
      utm_term: "meta-kw",
      landing_path: "/",
    });
    expect(attributionPayload()).toEqual({
      utm_term: "meta-kw",
      landing_path: "/",
    });
    expect(hasCampaignAttribution({ utm_term: "meta-kw" })).toBe(true);
    expect(authLoginPathFromSearch("utm_term=meta-kw&next=/admin")).toBe(
      "/?utm_term=meta-kw&auth=login",
    );
    const tooLong = `kw-${"a".repeat(400)}`;
    const bounced = authLoginPathFromSearch(`utm_term=${tooLong}&next=/admin`);
    expect(new URLSearchParams(bounced.slice(2)).get("utm_term")).toHaveLength(256);
    expect(authLoginPathFromSearch("utm_term=%00%07meta-kw")).toBe(
      "/?utm_term=meta-kw&auth=login",
    );
  });

  test("rejects case, padding, control chars, and duplicate starters on both parsers", () => {
    const rejected = [
      "starter=BACKTEST",
      "starter=SaViNgs",
      "starter=%20backtest%20",
      "starter=back%09test",
      "starter=backtest%00",
      "starter=backtest&starter=evil",
      "starter=evil&starter=backtest",
      "starter=backtest&starter=backtest",
    ];
    for (const search of rejected) {
      expect(parseLandingStarter(search)).toBeUndefined();
      expect(parseLandingIntent(search).starter).toBeUndefined();
      expect(authLoginPathFromSearch(search)).toBe("/?auth=login");
      expect(
        authLoginPathFromSearch(`utm_campaign=x&${search}`),
      ).toBe("/?utm_campaign=x&auth=login");
    }
  });

  test("%62acktest decodes to backtest through URLSearchParams, so it is accepted", () => {
    const params = new URLSearchParams("starter=%62acktest");
    expect(params.get("starter")).toBe("backtest");
    expect(params.getAll("starter")).toEqual(["backtest"]);
    expect(parseLandingStarter("starter=%62acktest")).toBe("backtest");
    expect(parseLandingIntent("starter=%62acktest").starter).toBe("backtest");
    expect(authLoginPathFromSearch("starter=%62acktest")).toBe(
      "/?starter=backtest&auth=login",
    );
  });
});

describe("landing intent storage", () => {
  test("first-touch keeps the first attributed visit as a whole", () => {
    installStorage();

    expect(
      captureLandingIntent("utm_campaign=x&starter=backtest", "/"),
    ).toEqual({
      utm_campaign: "x",
      starter: "backtest",
      landing_path: "/",
    });
    expect(captureLandingIntent("utm_campaign=later&utm_source=ig", "/chat")).toEqual({
      utm_campaign: "x",
      starter: "backtest",
      landing_path: "/",
    });
    expect(captureLandingIntent("", "/settings")).toEqual({
      utm_campaign: "x",
      starter: "backtest",
      landing_path: "/",
    });
    expect(readLandingIntent()?.utm_campaign).toBe("x");
    expect(readLandingIntent()?.utm_source).toBeUndefined();
    expect(JSON.parse(window.localStorage.getItem(LANDING_INTENT_STORAGE_KEY) ?? "{}")).toMatchObject({
      utm_campaign: "x",
      landing_path: "/",
    });
  });

  test("does not invent a capture from an empty visit", () => {
    installStorage();
    expect(captureLandingIntent("", "")).toBeNull();
    expect(readLandingIntent()).toBeNull();
    expect(window.localStorage.getItem(LANDING_INTENT_STORAGE_KEY)).toBeNull();
  });

  test("omits empty attribution and treats campaign-less paths as no campaign", () => {
    expect(attributionPayload(null)).toBeUndefined();
    expect(attributionPayload({ landing_path: "/" })).toEqual({
      landing_path: "/",
    });
    expect(hasCampaignAttribution({ landing_path: "/" })).toBe(false);
    expect(hasCampaignAttribution({ starter: "backtest" })).toBe(false);
    expect(hasCampaignAttribution({ ref: "stories" })).toBe(true);
    expect(hasCampaignAttribution({ utm_campaign: "x" })).toBe(true);
    expect(hasCampaignAttribution({ utm_term: "meta-kw" })).toBe(true);
    for (const field of CAMPAIGN_VALUE_FIELDS) {
      expect(hasCampaignAttribution({ [field]: "x" })).toBe(true);
      expect(authLoginPathFromSearch(`${field}=x&next=/admin`)).toBe(
        `/?${field}=x&auth=login`,
      );
    }
  });

  test("starter prefill is consume-once session state, like receipt follow-up", () => {
    const { session } = installStorage();
    captureLandingIntent("starter=backtest&utm_campaign=x", "/");
    expect(session.get(LANDING_STARTER_STORAGE_KEY)).toBe("backtest");
    expect(takeLandingStarterPrefill()).toBe("backtest");
    expect(takeLandingStarterPrefill()).toBeNull();
    expect(landingStarterAppliedThisRuntime()).toBe("backtest");
    expect(readLandingIntent()?.starter).toBe("backtest");
  });

  test("runtime starter fallback expires so a later empty composer does not re-prefill", () => {
    installStorage();
    const now = { value: 1_700_000_000_000 };
    const originalNow = Date.now;
    Date.now = () => now.value;
    try {
      captureLandingIntent("starter=backtest", "/");
      expect(takeLandingStarterPrefill()).toBe("backtest");
      expect(landingStarterAppliedThisRuntime()).toBe("backtest");
      now.value += LANDING_STARTER_RUNTIME_FALLBACK_MS;
      expect(landingStarterAppliedThisRuntime()).toBe("backtest");
      now.value += 1;
      expect(landingStarterAppliedThisRuntime()).toBeNull();
    } finally {
      Date.now = originalNow;
    }
  });

  test("resetLandingStarterRuntime drops the fallback before New chat remounts", () => {
    installStorage();
    captureLandingIntent("starter=savings", "/");
    expect(takeLandingStarterPrefill()).toBe("savings");
    expect(landingStarterAppliedThisRuntime()).toBe("savings");
    const epoch = landingStarterSurfaceEpoch();
    resetLandingStarterRuntime();
    expect(landingStarterAppliedThisRuntime()).toBeNull();
    expect(landingStarterSurfaceEpoch()).toBe(epoch + 1);
  });

  test("a leftover starter query cannot recreate a consumed prefill", () => {
    const { location } = installStorage();
    location.search = "?utm_campaign=x&starter=backtest";
    location.pathname = "/chat";
    captureLandingIntent(location.search, location.pathname);
    expect(takeLandingStarterPrefill()).toBe("backtest");
    stripLandingStarterFromLocation();
    expect(location.search).toBe("?utm_campaign=x");
    expect(captureLandingIntent(location.search, location.pathname)).toEqual({
      utm_campaign: "x",
      starter: "backtest",
      landing_path: "/chat",
    });
    expect(takeLandingStarterPrefill()).toBeNull();
    captureLandingIntent("starter=backtest&utm_campaign=x", "/chat");
    expect(takeLandingStarterPrefill()).toBeNull();
  });

  test("auth handoff restores the unused starter once without leftover-url replay", () => {
    const { location } = installStorage();
    location.search = "?utm_campaign=x&starter=backtest";
    location.pathname = "/chat";
    captureLandingIntent(location.search, location.pathname);
    expect(takeLandingStarterPrefill()).toBe("backtest");
    stripLandingStarterFromLocation();
    noteLandingStarterComposerMatch(true);
    prepareLandingStarterAuthHandoff();
    location.search = "?utm_campaign=x&starter=backtest";
    captureLandingIntent(location.search, location.pathname);
    expect(takeLandingStarterPrefill()).toBe("backtest");
    expect(takeLandingStarterPrefill()).toBeNull();
    captureLandingIntent("starter=backtest&utm_campaign=x", "/chat");
    expect(takeLandingStarterPrefill()).toBeNull();
  });

  test("New chat consumes a handoff so the composer stays empty", () => {
    installStorage();
    captureLandingIntent("starter=savings", "/");
    prepareLandingStarterAuthHandoff();
    const epoch = landingStarterSurfaceEpoch();
    resetLandingStarterRuntime();
    expect(takeLandingStarterPrefill()).toBeNull();
    expect(landingStarterAppliedThisRuntime()).toBeNull();
    expect(landingStarterSurfaceEpoch()).toBe(epoch + 1);
  });

  test("New chat keeps a pending starter that was never applied", () => {
    installStorage();
    captureLandingIntent("starter=savings", "/");
    const epoch = landingStarterSurfaceEpoch();
    resetLandingStarterRuntime();
    expect(takeLandingStarterPrefill()).toBe("savings");
    expect(landingStarterSurfaceEpoch()).toBe(epoch + 1);
  });

  test("auth handoff restores a consumed starter only while the composer is untouched", () => {
    installStorage();
    captureLandingIntent("starter=backtest", "/");
    expect(takeLandingStarterPrefill()).toBe("backtest");
    noteLandingStarterComposerMatch(true);
    prepareLandingStarterAuthHandoff();
    expect(takeLandingStarterPrefill()).toBe("backtest");
    noteLandingStarterComposerMatch(false);
    prepareLandingStarterAuthHandoff();
    expect(takeLandingStarterPrefill()).toBeNull();
  });

  test("a starter-only first visit does not lock out a later utm touch", () => {
    installStorage();
    expect(captureLandingIntent("starter=backtest", "/")).toBeNull();
    expect(readLandingIntent()).toBeNull();
    expect(window.localStorage.getItem(LANDING_INTENT_STORAGE_KEY)).toBeNull();
    expect(takeLandingStarterPrefill()).toBe("backtest");
    expect(
      captureLandingIntent("utm_campaign=x&utm_source=ig", "/chat"),
    ).toEqual({
      utm_campaign: "x",
      utm_source: "ig",
      landing_path: "/chat",
    });
    expect(readLandingIntent()).toEqual({
      utm_campaign: "x",
      utm_source: "ig",
      landing_path: "/chat",
    });
  });

  test("landing path is stored only with the campaign visit that owns it", () => {
    installStorage();
    expect(captureLandingIntent("", "/")).toBeNull();
    expect(readLandingIntent()).toBeNull();
    expect(
      captureLandingIntent("utm_campaign=x", "/r/abcdefghijklmnopqrstuvwx"),
    ).toEqual({
      utm_campaign: "x",
      landing_path: "/r/abcdefghijklmnopqrstuvwx",
    });
  });

  test("first-touch keeps a shared-thread landing path", () => {
    installStorage();
    expect(
      captureLandingIntent("utm_campaign=x&fbclid=abc.1", "/r/abcdefghijklmnopqrstuvwx"),
    ).toEqual({
      utm_campaign: "x",
      fbclid: "abc.1",
      landing_path: "/r/abcdefghijklmnopqrstuvwx",
    });
    expect(captureLandingIntent("utm_campaign=later", "/chat")).toEqual({
      utm_campaign: "x",
      fbclid: "abc.1",
      landing_path: "/r/abcdefghijklmnopqrstuvwx",
    });
  });

  test("this visit can prefill a new starter without rewriting first-touch attribution", () => {
    installStorage();
    captureLandingIntent("starter=backtest&utm_campaign=x", "/");
    expect(takeLandingStarterPrefill()).toBe("backtest");
    captureLandingIntent("starter=savings", "/chat");
    expect(takeLandingStarterPrefill()).toBe("savings");
    expect(readLandingIntent()).toEqual({
      utm_campaign: "x",
      starter: "backtest",
      landing_path: "/",
    });
  });

  test("rejects stored payloads that fail the same sanitizers as the URL", () => {
    installStorage();
    window.localStorage.setItem(
      LANDING_INTENT_STORAGE_KEY,
      JSON.stringify({
        utm_campaign: "\u0000",
        starter: "hold",
        landing_path: "//evil",
        extra: "drop-me",
      }),
    );
    expect(readLandingIntent()).toBeNull();
  });

  test("keeps stored campaign punctuation that is not starter text", () => {
    installStorage();
    window.localStorage.setItem(
      LANDING_INTENT_STORAGE_KEY,
      JSON.stringify({
        utm_campaign: "<script>",
        starter: "hold",
        landing_path: "//evil",
      }),
    );
    expect(readLandingIntent()).toEqual({ utm_campaign: "<script>" });
  });
});

describe("landing starter prefill wiring", () => {
  const root = join(import.meta.dir, "..");

  test("reuses the receipt-followup consume-once hook and never auto-sends", () => {
    const hook = readFileSync(
      join(root, "components/chat/useLandingStarterPrefill.ts"),
      "utf-8",
    );
    const empty = readFileSync(
      join(root, "components/chat/EmptyChatSurface.tsx"),
      "utf-8",
    );
    const input = readFileSync(
      join(root, "components/chat/ChatInput.tsx"),
      "utf-8",
    );

    expect(hook).toContain("takeLandingStarterPrefill");
    expect(hook).toContain("captureLandingIntentFromLocation");
    expect(hook).toContain("stripLandingStarterFromLocation");
    expect(hook).toContain("landingStarterAppliedThisRuntime");
    expect(hook).toContain("landingStarterSurfaceEpoch");
    expect(hook).toContain("if (!canConsume) return");
    expect(hook).not.toContain("onSend");
    expect(hook).not.toContain("admitSend");
    expect(empty).toContain("useLandingStarterPrefill(canConsumeLandingStarter && !workspace)");
    expect(empty).toContain("canConsumeLandingStarter");
    expect(empty).toContain("draftText={draftText}");
    expect(empty).toContain(
      "`new-conversation-${landingStarterSurfaceEpoch()}`",
    );
    expect(input).toContain("draftText");
    expect(input).not.toContain("onSend(draftText");
    expect(input).toContain("if (composerHasContent || composerRawText.trim())");
    expect(input).toContain("noteLandingStarterComposerMatch");

    const lifecycle = readFileSync(
      join(root, "components/chat/useChatSurfaceLifecycle.ts"),
      "utf-8",
    );
    const startBlock = lifecycle.slice(
      lifecycle.indexOf("const startNewChat"),
      lifecycle.indexOf("const handleConversationRemoved"),
    );
    expect(startBlock).toContain("resetLandingStarterRuntime()");

    const init = readFileSync(
      join(root, "components/chat/useInitialChatSession.ts"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    expect(init).toContain("setInitialRoutingSettled(true)");
    expect(init).toContain("return initialRoutingSettled");
    expect(chat).toContain("canConsumeLandingStarter={initialRoutingSettled}");
    expect(chat).not.toContain("admitSend");
  });

  test("public receipt landings capture the live path before a follow-up forks", () => {
    const layout = readFileSync(join(root, "app/r/layout.tsx"), "utf-8");
    const followup = readFileSync(
      join(root, "components/receipt/ReceiptFollowup.tsx"),
      "utf-8",
    );
    const capture = readFileSync(
      join(root, "components/receipt/LandingIntentCapture.tsx"),
      "utf-8",
    );
    expect(layout).toContain("LandingIntentCapture");
    expect(capture).toContain("captureLandingIntentFromLocation");
    expect(followup).toContain("captureLandingIntentFromLocation");
    expect(followup).toContain("receiptFollowupTarget()");
    expect(followup).not.toContain('router.push("/chat")');
  });

  test("Playwright config owns the mock-signup network flag instead of webdriver", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");
    const playwright = readFileSync(join(root, "playwright.config.ts"), "utf-8");
    expect(page).toContain("NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP");
    expect(page).not.toContain("navigator.webdriver");
    expect(playwright).toContain('NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP: "true"');
  });
});

describe("landing intent merge and redirects", () => {
  test("merge keeps the first attributed visit instead of stitching later fields", () => {
    expect(
      mergeFirstTouchLandingIntent(
        { utm_source: "facebook" },
        { utm_campaign: "summer", utm_medium: "email" },
      ),
    ).toEqual({
      utm_source: "facebook",
    });
    expect(
      mergeFirstTouchLandingIntent(null, {
        utm_campaign: "summer",
        landing_path: "/r/abcdefghijklmnopqrstuvwx",
      }),
    ).toEqual({
      utm_campaign: "summer",
      landing_path: "/r/abcdefghijklmnopqrstuvwx",
    });
    expect(
      mergeFirstTouchLandingIntent(
        { landing_path: "/" },
        { utm_campaign: "x", landing_path: "/chat" },
      ),
    ).toEqual({
      utm_campaign: "x",
      landing_path: "/chat",
    });
  });

  test("preserves query params onto chat and login redirects", () => {
    expect(pathWithSearch("/chat", "?utm_campaign=x&starter=backtest&auth=signup")).toBe(
      "/chat?utm_campaign=x&starter=backtest",
    );
    expect(authLoginPathFromSearch("utm_campaign=x&utm_term=meta-kw&starter=backtest")).toBe(
      "/?utm_campaign=x&utm_term=meta-kw&starter=backtest&auth=login",
    );
    expect(authLoginPathFromSearch("utm_campaign=x", "/chat")).toBe(
      "/?utm_campaign=x&from_path=%2Fchat&auth=login",
    );
    expect(parseLandingIntent("utm_campaign=x&from_path=/chat", "/")).toEqual({
      utm_campaign: "x",
      landing_path: "/chat",
    });
    expect(parseLandingIntent("utm_campaign=x&from_path=/settings", "/")).toEqual({
      utm_campaign: "x",
      landing_path: "/",
    });
    expect(
      authLoginPathFromSearch({
        utm_campaign: "x",
        starter: ["backtest", "ignored"],
      }),
    ).toBe("/?utm_campaign=x&auth=login");
    (globalThis as { window?: { location: { search: string } } }).window = {
      location: { search: "?utm_campaign=x" },
    };
    expect(currentChatPath()).toBe("/chat?utm_campaign=x");
    // The signed-in home: chat on a consumer build, the Business workspace on a Business build.
    expect(signedInHomePath(false, false)).toBe("/chat?utm_campaign=x");
    expect(signedInHomePath(true, false)).toBe("/biz");
    expect(postAuthPath(false, false)).toBe("/chat?utm_campaign=x");
    expect(postAuthPath(true, false)).toBe("/biz");
    // A listed return page wins on either build; anything else is ignored.
    (globalThis as { window?: { location: { search: string } } }).window = {
      location: { search: "?return_to=%2Fbiz%3Freceipt%3Dr1&auth=login" },
    };
    expect(postAuthPath(true, false)).toBe("/biz?receipt=r1");
    expect(postAuthPath(false, false)).toBe("/biz?receipt=r1");
    (globalThis as { window?: { location: { search: string } } }).window = {
      location: { search: "?return_to=https%3A%2F%2Fevil.example%2Fbiz" },
    };
    expect(postAuthPath(true)).toBe("/biz");
    // Protocol-relative, backslash, scheme and encoded spellings of another host all fall back to home.
    for (const hostile of [
      "%2F%2Fevil.example",
      "%2F%5Cevil.example%2Fbiz",
      "/\\evil.example",
      "javascript%3Aalert(1)",
      "%2Fbiz%2F..%2F..%2F%2Fevil.example",
      "%252F%252Fevil.example",
      "https%3A%2F%2Fevil.example%2Fbiz",
      "%2Fchat",
    ]) {
      (globalThis as { window?: { location: { search: string } } }).window = {
        location: { search: `?return_to=${hostile}` },
      };
      expect(postAuthPath(true, false)).toBe("/biz");
      expect(postAuthPath(false, false)).toBe("/chat");
    }
    // A listed page carrying junk keeps only its listed keys: the junk is dropped, the page stays.
    (globalThis as { window?: { location: { search: string } } }).window = {
      location: { search: "?return_to=%2Fbiz%3Freturn_to%3D%2F%2Fevil.example%26receipt%3Dr9" },
    };
    expect(postAuthPath(false, false)).toBe("/biz?receipt=r9");
    delete (globalThis as { window?: unknown }).window;
    // The Business shell path keeps only the conversation and message a chat address named.
    expect(businessShellPath("conversation=c1&message=m2&auth=login&next=%2Fadmin")).toBe("/biz?conversation=c1&message=m2");
    expect(businessShellPath("conversation=%2F%2Fevil")).toBe("/biz");
    expect(businessShellPath("")).toBe("/biz");
  });

  test("login bounce drops next, redirect, unknown params, and invalid starters", () => {
    expect(
      authLoginPathFromSearch(
        "utm_campaign=x&utm_term=meta-kw&starter=backtest&next=/admin&redirect=https://evil.example&foo=1&auth=signup",
      ),
    ).toBe("/?utm_campaign=x&utm_term=meta-kw&starter=backtest&auth=login");
    expect(
      authLoginPathFromSearch("utm_campaign=x&starter=BACKTEST&next=/admin"),
    ).toBe("/?utm_campaign=x&auth=login");
    expect(
      authLoginPathFromSearch(
        "starter=evil&starter=backtest&next=/settings&redirect=/",
        "/chat",
      ),
    ).toBe("/?from_path=%2Fchat&auth=login");
  });

  test("business-only never targets chat, signed in or signed out", () => {
    const chatPath = "/chat";
    const rows = [
      [true, false, false, { href: chatPath }],
      [true, true, false, { href: "/biz" }],
      [true, true, true, { href: "/biz" }],
      [true, false, true, { closed: true }],
      [false, false, false, { href: chatPath }],
      [false, true, false, { href: "/?auth=login" }],
      [false, true, true, { href: "/?auth=login" }],
      [false, false, true, { href: "/?auth=login" }],
    ] as const;
    for (const [signedIn, pilot, businessOnly, expected] of rows) {
      const target = homeTarget({ signedIn, pilot, businessOnly, chatPath });
      expect(target).toEqual(expected);
      if (businessOnly) {
        expect("href" in target ? target.href : "/?auth=login").not.toMatch(/^\/chat/);
      }
    }
    expect(businessShellEntry({ pilot: false, businessOnly: true })).toEqual({ closed: true });
  });
});
