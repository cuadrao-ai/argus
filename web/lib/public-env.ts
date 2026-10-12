/**
 * Public build-time settings under their Cuadrao names, with the Argus names
 * as a fallback. Next inlines only literal `process.env.NAME` reads, so each
 * pair is spelled out here and read nowhere else. They are functions, not
 * constants, so a test can set the environment before reading.
 */
function first(...values: Array<string | undefined>): string | undefined {
  for (const value of values) {
    if (value !== undefined && value.trim() !== "") return value;
  }
  return undefined;
}

export function publicApiUrl(): string | undefined {
  return first(process.env.NEXT_PUBLIC_CUADRAO_API_URL, process.env.NEXT_PUBLIC_ARGUS_API_URL);
}

export function publicTurnstileSiteKey(): string | undefined {
  return first(process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY, process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY);
}

export function publicLocalQaCaptchaToken(): string | undefined {
  return first(
    process.env.NEXT_PUBLIC_CUADRAO_LOCAL_QA_CAPTCHA_TOKEN,
    process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN,
  );
}
