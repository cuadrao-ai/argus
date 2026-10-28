import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { renderExistingAccountEmail } from "../../marketing/lib/email/existing-account";
import spanish from "../public/locales/es-419/common.json";
import english from "../public/locales/en/common.json";
import { assertEmailPresentation } from "./helpers/email-presentation";

const signInUrl = "https://app.example.test/?auth=login";

for (const locale of ["es-419", "en"] as const) {
  test(`existing account email renders ${locale} copy with one sign-in action`, () => {
    const copy = (locale === "en" ? english : spanish).account_email.existing_account;
    const rendered = renderExistingAccountEmail({ signInUrl }, { locale, assetOrigin: "https://assets.example.test" });
    expect(rendered.subject).toBe(copy.subject);
    for (const paragraph of copy.paragraphs) expect(rendered.text).toContain(paragraph);
    expect(rendered.text).toContain(`${copy.cta}\n${signInUrl}`);
    expect(rendered.text).toContain(copy.after_action);
    expect(rendered.html.match(/class="button"/g)).toHaveLength(1);
    expect(`${rendered.html}${rendered.text}`).not.toContain("—");
    assertEmailPresentation(rendered.html, rendered.text);
  });
}

test("existing account email links only to ordinary sign-in", () => {
  for (const url of ["http://app.example.test/?auth=login", "https://app.example.test/?auth=signup", "https://app.example.test/biz?auth=login", "https://user:pass@app.example.test/?auth=login", `${signInUrl}#x`]) {
    expect(() => renderExistingAccountEmail({ signInUrl: url })).toThrow();
  }
});

test("Python artifact is derived from the renderer", () => {
  const result = spawnSync("bun", ["scripts/emails/sync-existing-account.ts", "--check"], { cwd: new URL("../../", import.meta.url), encoding: "utf8" });
  expect(result.status).toBe(0);
});
