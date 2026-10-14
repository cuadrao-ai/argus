import { afterEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const originalFetch = globalThis.fetch;
const webRoot = join(import.meta.dir, "..");

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("public alpha access request client", () => {
  test("posts the selected language and returns the generic accepted result", async () => {
    const guestApi = await import("../lib/guest-api");
    const requestAccess = (
      guestApi as Record<string, unknown>
    ).requestAccess as
      | ((payload: {
          email: string;
          language: "en" | "es-419";
        }) => Promise<{ accepted: true }>)
      | undefined;
    expect(typeof requestAccess).toBe("function");
    if (!requestAccess) return;

    let requestUrl = "";
    let requestInit: RequestInit | undefined;
    globalThis.fetch = (async (input, init) => {
      requestUrl = String(input);
      requestInit = init;
      return new Response(JSON.stringify({ accepted: true }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof globalThis.fetch;

    const result = await requestAccess({
      email: "person@example.com",
      language: "es-419",
    });

    expect(new URL(requestUrl).pathname).toBe(
      "/api/v1/auth/access-requests",
    );
    expect(requestInit?.method).toBe("POST");
    expect(JSON.parse(String(requestInit?.body))).toEqual({
      email: "person@example.com",
      language: "es-419",
    });
    expect(result).toEqual({ accepted: true });
  });

  test("keeps every request state complete in English and Latin American Spanish", () => {
    const en = JSON.parse(
      readFileSync(
        join(webRoot, "public/locales/en/common.json"),
        "utf-8",
      ),
    );
    const es = JSON.parse(
      readFileSync(
        join(webRoot, "public/locales/es-419/common.json"),
        "utf-8",
      ),
    );

    expect(en.auth.access_request).toEqual({
      title: "Request access to Cuadrao",
      description:
        "Cuadrao is in early access. Share your email to request access. If approved, we’ll email you when you can create an account.",
      email_label: "Email address",
      submit: "Request access",
      submitting: "Requesting access...",
      accepted_title: "Request received",
      accepted_description:
        "Thanks, we received your request. If access is approved, we’ll email you with the next step.",
      approved_prompt: "Already approved?",
      approved_action: "Sign up",
      existing_prompt: "Already have an account?",
      existing_action: "Sign in",
      error:
        "We couldn’t send your request. Please try again.",
    });
    expect(es.auth.access_request).toEqual({
      title: "Solicita acceso a Cuadrao",
      description:
        "Cuadrao está en acceso anticipado. Comparte tu correo para solicitar acceso. Si se aprueba, te enviaremos un correo cuando puedas crear una cuenta.",
      email_label: "Correo electrónico",
      submit: "Solicitar acceso",
      submitting: "Solicitando acceso...",
      accepted_title: "Solicitud recibida",
      accepted_description:
        "Gracias. Recibimos tu solicitud. Si se aprueba el acceso, te enviaremos por correo el siguiente paso.",
      approved_prompt: "¿Ya recibiste aprobación?",
      approved_action: "Regístrate",
      existing_prompt: "¿Ya tienes una cuenta?",
      existing_action: "Inicia sesión",
      error:
        "No pudimos enviar tu solicitud. Inténtalo de nuevo.",
    });
  });
});
