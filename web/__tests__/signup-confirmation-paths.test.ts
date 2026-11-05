import { expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const webRoot = join(import.meta.dir, "..");

function spawn(fixture: string) {
  const result = Bun.spawnSync(
    [process.execPath, join(import.meta.dir, "fixtures/signup-email-code", fixture)],
    { cwd: webRoot },
  );
  expect(result.exitCode, `${result.stdout}\n${result.stderr}`).toBe(0);
}

test("verifyOtp receives every email OTP type when the browser client is used", () => {
  spawn("default-verify.ts");
});

test("a signup confirmation link installs the session and other email hashes do not", () => {
  spawn("signup-link.ts");
});

test("signup finishes from the code step, and the guest chat surfaces are gone", () => {
  const page = readFileSync(join(webRoot, "app/page.tsx"), "utf-8");
  const form = readFileSync(join(webRoot, "components/auth/AuthForm.tsx"), "utf-8");

  expect(page).toContain("onEmailConfirmed={finishConfirmedSignup}");
  expect(page).toContain("saveProfileLanguage");
  expect(form).toContain('data-testid="auth-confirmation-code"');
  expect(form).toContain('type: "signup"');

  const finishStart = page.indexOf("const finishConfirmedSignup");
  const finish = page.slice(finishStart, page.indexOf("const isSignup", finishStart));
  expect(finish).toContain("continueWithChosenLanguage");
  expect(finish).not.toContain("guest_claim");
  expect(finish).not.toContain("registerGuestAccount");

  for (const relativePath of [
    "components/guest/ExpiredGuestSession.tsx",
    "components/guest/GuestExperienceSurfaces.tsx",
    "components/guest/GuestConversionModal.tsx",
    "components/guest/useGuestConversion.ts",
  ]) {
    expect(existsSync(join(webRoot, relativePath))).toBe(false);
  }
});
