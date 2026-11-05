import {
  normalizeApiLanguage,
  persistBrowserSession,
  unauthenticatedApiFetch,
} from "./argus-api";
import { acquireGuestCaptchaToken } from "./guest-captcha";
import { attributionBody } from "./landing-intent";

export {
  guestCaptchaConfigured,
  guestCaptchaPlanForEnvironment,
  guestCaptchaTokenForEnvironment,
} from "./guest-captcha";

type GuestSessionInput = {
  language: string | null | undefined;
  captchaToken?: string | null;
};

export type GuestBootstrapResponse = {
  authenticated: true;
  reused: boolean;
  renewed_after_expiry?: boolean;
  public_account_access_enabled?: boolean;
  account_kind: "guest";
  session?: {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  } | null;
  user?: Record<string, unknown> | null;
};

export function createGuestSessionBootstrapper<
  TInput,
  TResult,
>(bootstrap: (input: TInput) => Promise<TResult>) {
  let pending: Promise<TResult> | null = null;

  return {
    run(input: TInput) {
      if (!pending) {
        const started = bootstrap(input).catch((error: unknown) => {
          if (pending === started) pending = null;
          throw error;
        });
        pending = started;
      }
      return pending;
    },
    reset() {
      pending = null;
    },
  };
}

let persistGuestBootstrap = true;
let guestBootstrapAbort: AbortController | null = null;

const browserGuestBootstrapper = createGuestSessionBootstrapper<
  GuestSessionInput,
  GuestBootstrapResponse
>(async ({ language, captchaToken: browserCaptchaToken }) => {
  const signal = guestBootstrapAbort?.signal;
  const captchaToken = await acquireGuestCaptchaToken(
    browserCaptchaToken,
    signal,
  );
  return bootstrapGuest({
    captcha_token: captchaToken,
    language: normalizeApiLanguage(language),
    signal,
  });
});

function guestBootstrapAbortError(): Error {
  const error = new Error("Guest bootstrap cancelled.");
  error.name = "AbortError";
  return error;
}

export function isGuestBootstrapAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name: string }).name === "AbortError"
  );
}

function armGuestBootstrapAbort() {
  if (!guestBootstrapAbort || guestBootstrapAbort.signal.aborted) {
    guestBootstrapAbort = new AbortController();
  }
}

export function resetGuestBootstrapRuntime() {
  persistGuestBootstrap = true;
  guestBootstrapAbort = null;
  browserGuestBootstrapper.reset();
}

export function cancelPendingGuestBootstrap() {
  persistGuestBootstrap = false;
  guestBootstrapAbort?.abort();
  browserGuestBootstrapper.reset();
}

export async function bootstrapGuest(payload: {
  captcha_token: string;
  language: "en" | "es-419";
  signal?: AbortSignal;
}) {
  const { signal, captcha_token, language } = payload;
  if (signal?.aborted || !persistGuestBootstrap) {
    throw guestBootstrapAbortError();
  }
  const response = await unauthenticatedApiFetch<GuestBootstrapResponse>(
    "/auth/guest",
    {
      method: "POST",
      body: JSON.stringify({ captcha_token, language, ...attributionBody() }),
      signal,
    },
  );
  if (signal?.aborted || !persistGuestBootstrap) {
    return response;
  }
  await persistBrowserSession(response);
  return response;
}

export function startGuestSession(
  language?: string | null,
  captchaToken?: string | null,
) {
  persistGuestBootstrap = true;
  armGuestBootstrapAbort();
  return browserGuestBootstrapper.run({ language, captchaToken });
}

export function retryGuestSession(
  language?: string | null,
  captchaToken?: string | null,
) {
  browserGuestBootstrapper.reset();
  return startGuestSession(language, captchaToken);
}
