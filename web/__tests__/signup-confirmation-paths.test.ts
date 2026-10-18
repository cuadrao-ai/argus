import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
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

test("signup, guest conversion, and expired guest all finish from the same code step", () => {
  const page = readFileSync(join(webRoot, "app/page.tsx"), "utf-8");
  const expired = readFileSync(
    join(webRoot, "components/guest/ExpiredGuestSession.tsx"),
    "utf-8",
  );
  const surfaces = readFileSync(
    join(webRoot, "components/guest/GuestExperienceSurfaces.tsx"),
    "utf-8",
  );
  const modal = readFileSync(
    join(webRoot, "components/guest/GuestConversionModal.tsx"),
    "utf-8",
  );
  const hook = readFileSync(
    join(webRoot, "components/guest/useGuestConversion.ts"),
    "utf-8",
  );
  const form = readFileSync(join(webRoot, "components/auth/AuthForm.tsx"), "utf-8");

  expect(page).toContain("onEmailConfirmed={finishConfirmedSignup}");
  expect(page).toContain("saveProfileLanguage");
  expect(expired).toContain("onEmailConfirmed=");
  expect(expired).toContain("postAuthPath(businessBuild)");
  expect(surfaces).toContain("onEmailConfirmed={conversion.finishConfirmedSignup}");
  expect(modal).toContain("onEmailConfirmed={onEmailConfirmed}");
  expect(form).toContain('data-testid="auth-confirmation-code"');
  expect(form).toContain('type: "signup"');

  const finishStart = hook.indexOf("const finishConfirmedSignup");
  const finish = hook.slice(finishStart, hook.indexOf("\n  return {", finishStart));
  expect(finish).toContain("await getMe(");
  expect(finish).toContain("refreshAccount(");
  expect(finish).toContain("setIsOpen(false)");
  expect(finish).not.toContain("guest_claim");
  expect(finish).not.toContain("registerGuestAccount");
  expect(finish).not.toContain("await refreshHistory()");
  expect(hook).toContain("finishConfirmedSignup,");
});
