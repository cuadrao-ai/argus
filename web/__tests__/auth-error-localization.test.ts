import { describe, expect, test } from "bun:test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

type LocaleTree = Record<string, unknown>;
type AuthErrorTranslator = (key: string, fallback: string) => string;
type AuthErrorResolver = (
  error: unknown,
  translate: AuthErrorTranslator,
) => string;

const mappedCodes = [
  "captcha_unavailable",
  "unauthorized",
  "auth_signup_failed",
  "too_many_requests",
  "guest_access_unavailable",
  "internal_error",
  "account_already_registered",
  "account_exists_use_login",
  "guest_bootstrap_failed",
  "guest_identity_link_failed",
  "csrf_origin_rejected",
  "registered_account_required",
  "access_request_unavailable",
  "public_account_access_unavailable",
  "guest_session_expired",
  "guest_handoff_invalid",
  "guest_handoff_consumed",
  "guest_handoff_expired",
  "guest_handoff_wrong_destination",
  "guest_handoff_source_not_anonymous",
  "guest_handoff_unsafe_product_graph",
  "guest_handoff_workspace_unavailable",
  "guest_handoff_claim_unavailable",
  "otp_rejected",
] as const;

function translator(catalog: LocaleTree): AuthErrorTranslator {
  return (key, fallback) => {
    const value = key.split(".").reduce<unknown>((current, segment) => {
      if (typeof current !== "object" || current === null) return undefined;
      return (current as LocaleTree)[segment];
    }, catalog);
    return typeof value === "string" ? value : fallback;
  };
}

function codedError(code: string, rawMessage = "raw backend detail"): Error {
  return Object.assign(new Error(rawMessage), { code });
}

async function resolver(): Promise<AuthErrorResolver> {
  const authFormModule = await import("../components/auth/AuthForm");
  const candidate = (
    authFormModule as { localizedAuthErrorMessage?: AuthErrorResolver }
  ).localizedAuthErrorMessage;
  return candidate ?? (() => "__missing_auth_error_resolver__");
}

describe("auth error localization", () => {
  test("maps every known auth code in English and es-419", async () => {
    const resolve = await resolver();
    const translateEn = translator(en);
    const translateEs = translator(es419);
    const genericEn = translateEn("auth.errors.generic", "");
    const genericEs = translateEs("auth.errors.generic", "");

    for (const code of mappedCodes) {
      expect(resolve(codedError(code), translateEn), `${code} English`).not.toBe(
        genericEn,
      );
      expect(resolve(codedError(code), translateEs), `${code} es-419`).not.toBe(
        genericEs,
      );
    }
  });

  test("renders distinct localized messages without backend prose", async () => {
    const resolve = await resolver();

    expect(resolve(codedError("unauthorized"), translator(en))).toBe(
      "We couldn’t verify those account details. Check them and try again.",
    );
    expect(resolve(codedError("unauthorized"), translator(es419))).toBe(
      "No pudimos verificar los datos de la cuenta. Revísalos e inténtalo de nuevo.",
    );
    expect(resolve(codedError("guest_handoff_expired"), translator(en))).toBe(
      "The transfer expired. Start the sign-in flow again.",
    );
    expect(
      resolve(codedError("guest_handoff_expired"), translator(es419)),
    ).toBe(
      "La transferencia venció. Inicia el proceso de inicio de sesión de nuevo.",
    );
    expect(resolve(codedError("csrf_origin_rejected"), translator(en))).toBe(
      "We couldn’t verify this request. Refresh the page and try again.",
    );
    expect(
      resolve(codedError("csrf_origin_rejected"), translator(es419)),
    ).toBe(
      "No pudimos verificar esta solicitud. Actualiza la página e inténtalo de nuevo.",
    );
    expect(resolve(codedError("captcha_unavailable"), translator(en))).toBe(
      "We couldn’t verify your browser. Try again.",
    );
    expect(
      resolve(codedError("captcha_unavailable"), translator(es419)),
    ).toBe(
      "No pudimos verificar tu navegador. Intenta de nuevo.",
    );
    expect(resolve(codedError("captcha_unavailable"), translator(en))).not.toBe(
      "captcha_unavailable",
    );
    expect(resolve(codedError("otp_rejected"), translator(en))).toBe(
      "That code was not accepted. Check the email and try again.",
    );
    expect(resolve(codedError("otp_rejected"), translator(es419))).toBe(
      "Ese código no fue aceptado. Revisa el correo e inténtalo de nuevo.",
    );
  });

  test("falls back to the localized generic message for unknown errors", async () => {
    const resolve = await resolver();

    expect(
      resolve(
        codedError("future_auth_code", "future raw backend detail"),
        translator(en),
      ),
    ).toBe("Something went wrong. Please try again.");
    expect(
      resolve(
        codedError("future_auth_code", "future raw backend detail"),
        translator(es419),
      ),
    ).toBe("Algo salio mal. Intentalo de nuevo.");
    expect(resolve(new Error("uncoded raw detail"), translator(en))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});
