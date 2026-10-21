import { afterEach, describe, expect, test } from "bun:test";

import PrivacyPage from "../app/privacy/page";
import TermsPage from "../app/terms/page";

const ENV_NAMES = ["NEXT_PUBLIC_CUADRAO_TERMS_URL", "NEXT_PUBLIC_CUADRAO_PRIVACY_URL"] as const;

function redirectedTo(page: () => unknown): string {
  try {
    page();
  } catch (error) {
    const digest = (error as { digest?: unknown }).digest;
    if (typeof digest === "string" && digest.startsWith("NEXT_REDIRECT;")) {
      return digest.split(";")[2]!;
    }
    throw error;
  }
  throw new Error("the page rendered instead of redirecting");
}

afterEach(() => {
  for (const name of ENV_NAMES) delete process.env[name];
});

describe("the old /terms and /privacy routes send readers to the published pages", () => {
  test("with nothing set, they redirect to cuadrao.ai", () => {
    expect(redirectedTo(TermsPage)).toBe("https://cuadrao.ai/terminos");
    expect(redirectedTo(PrivacyPage)).toBe("https://cuadrao.ai/privacidad");
  });

  test("a set URL wins over the published one", () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = "https://cuadrao.example/privacidad";
    expect(redirectedTo(TermsPage)).toBe("https://cuadrao.example/terminos");
    expect(redirectedTo(PrivacyPage)).toBe("https://cuadrao.example/privacidad");
  });

  test("a blank setting falls back to the published page", () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "   ";
    expect(redirectedTo(TermsPage)).toBe("https://cuadrao.ai/terminos");
  });
});
