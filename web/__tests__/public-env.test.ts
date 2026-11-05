import { expect, test } from "bun:test";
import { publicApiUrl, publicLocalQaCaptchaToken, publicTurnstileSiteKey } from "../lib/public-env";

/* The Cuadrao name wins when both are set; the Argus name still works alone; blank counts as unset. */
test("public settings read the Cuadrao name first and fall back to the Argus name", () => {
  process.env.NEXT_PUBLIC_CUADRAO_API_URL = "http://cuadrao.test/api/v1";
  process.env.NEXT_PUBLIC_ARGUS_API_URL = "http://argus.test/api/v1";
  expect(publicApiUrl()).toBe("http://cuadrao.test/api/v1");
  delete process.env.NEXT_PUBLIC_CUADRAO_API_URL;
  expect(publicApiUrl()).toBe("http://argus.test/api/v1");
  process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY = "   ";
  process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY = "site-key";
  expect(publicTurnstileSiteKey()).toBe("site-key");
  delete process.env.NEXT_PUBLIC_CUADRAO_LOCAL_QA_CAPTCHA_TOKEN;
  delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
  expect(publicLocalQaCaptchaToken()).toBeUndefined();
});
