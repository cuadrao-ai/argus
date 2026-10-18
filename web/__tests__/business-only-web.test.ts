import { describe, expect, test } from "bun:test";
import { NextRequest } from "next/server";

import {
  decideBusinessOnlyWeb,
  type BusinessOnlyDecision,
} from "../lib/business-only-web";
import { businessOnlyWebFromEnv } from "../lib/private-alpha-flags";
import { proxy } from "../proxy";

function decision(
  pathname: string,
  search = "",
  enabled = true,
): BusinessOnlyDecision {
  return decideBusinessOnlyWeb({ enabled, pathname, search });
}

describe("businessOnlyWebFromEnv", () => {
  test("is on unless the value is the string false", () => {
    expect(businessOnlyWebFromEnv(undefined)).toBe(true);
    expect(businessOnlyWebFromEnv("")).toBe(true);
    expect(businessOnlyWebFromEnv("true")).toBe(true);
    expect(businessOnlyWebFromEnv("FALSE")).toBe(true);
    expect(businessOnlyWebFromEnv("false")).toBe(false);
  });
});

describe("decideBusinessOnlyWeb", () => {
  test("sends the root, guest entry, and legacy chat routes to business sign-in", () => {
    for (const pathname of [
      "/",
      "/chat",
      "/chat/",
      "/chat/history",
      "/chat/conversation/abc",
      "/login",
      "/signup",
    ]) {
      expect(decision(pathname)).toEqual({
        action: "redirect",
        location: "/?auth=login",
      });
    }
  });

  test("sends a guest-session landing and request-access to business sign-in", () => {
    expect(decision("/chat", "?conversation=guest-1")).toEqual({
      action: "redirect",
      location: "/?auth=login",
    });
    expect(decision("/", "?auth=request")).toEqual({
      action: "redirect",
      location: "/?auth=login",
    });
    expect(decision("/", "?starter=backtest")).toEqual({
      action: "redirect",
      location: "/?starter=backtest&auth=login",
    });
    expect(decision("/", "?utm_campaign=spring")).toEqual({
      action: "redirect",
      location: "/?utm_campaign=spring&auth=login",
    });
  });

  test("leaves business sign-in, sign-up, and the allowlist in place", () => {
    const stayed = [
      ["/", "?auth=login"],
      ["/", "?auth=signup"],
      ["/privacy", ""],
      ["/terms", ""],
      ["/health", ""],
      ["/auth/recovery", ""],
      ["/auth/forgot-password", ""],
      ["/auth/native-captcha", ""],
      ["/api/auth/recovery", ""],
      ["/api/auth/send-email", ""],
      ["/account/security", ""],
      ["/account/delete", ""],
      ["/r/receipt-1", ""],
      ["/biz", ""],
      ["/biz/inbox", ""],
      ["/locales/en/common.json", ""],
      ["/icons/cuadrao-192.png", ""],
      ["/_next/static/chunks/a.js", ""],
      ["/unknown", ""],
    ] as const;

    for (const [pathname, search] of stayed) {
      expect(decision(pathname, search)).toEqual({ action: "next" });
    }
  });

  test("restores today's routes when the switch is off", () => {
    for (const pathname of ["/", "/chat", "/chat/history", "/login", "/signup"]) {
      expect(decision(pathname, "", false)).toEqual({ action: "next" });
    }
  });
});

describe("proxy", () => {
  const previous = process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB;

  function restore() {
    if (previous === undefined) {
      delete process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB;
    } else {
      process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB = previous;
    }
  }

  test("redirects /chat to business sign-in when the switch is on", () => {
    delete process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB;
    try {
      const response = proxy(new NextRequest("http://localhost/chat"));
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "http://localhost/?auth=login",
      );
    } finally {
      restore();
    }
  });

  test("lets /chat through when the switch is off", () => {
    process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB = "false";
    try {
      const response = proxy(new NextRequest("http://localhost/chat"));
      expect(response.headers.get("location")).toBeNull();
      expect(response.status).not.toBe(307);
    } finally {
      restore();
    }
  });

  test("keeps an auth callback and the legal pages", () => {
    delete process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB;
    try {
      for (const path of ["/auth/recovery", "/privacy", "/terms", "/account/security"]) {
        const response = proxy(new NextRequest(`http://localhost${path}`));
        expect(response.headers.get("location")).toBeNull();
      }
    } finally {
      restore();
    }
  });
});
