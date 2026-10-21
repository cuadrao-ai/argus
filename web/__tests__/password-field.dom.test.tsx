import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { PASSWORD_MIN_LENGTH, readPassword } from "@/lib/password-strength";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/password" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

/** Random consonants with no repeat or alphabet step between neighbours, so no word, run or repeat by chance. */
function randomLetters(count: number): string {
  const letters = "bcdfghjkmnpqrstvwxz";
  let out = "";
  while (out.length < count) {
    const next = letters[Math.floor(Math.random() * letters.length)];
    const last = out.at(-1);
    if (last && Math.abs(next.charCodeAt(0) - last.charCodeAt(0)) <= 1) continue;
    out += next;
  }
  return out;
}

describe("password strength is entropy, not checkboxes", () => {
  test("the one hard rule is the auth server's minimum, with no composition rule", () => {
    const config = readFileSync(join(import.meta.dir, "../../supabase/config.toml"), "utf8");
    assert.equal(Number(config.match(/^minimum_password_length = (\d+)$/m)?.[1]), PASSWORD_MIN_LENGTH);
    assert.match(config, /^password_requirements = ""$/m);
  });

  test("a word with a capital and a digit passes every checkbox and is still weak", () => {
    for (const password of ["Password0", "Contraseña1", "Qwerty123!", "12345678", "aaaaaaaaaaaa", "abcdefgh"]) {
      assert.equal(readPassword(password).strength, "weak", password);
    }
  });

  test("length beats symbols", () => {
    assert.equal(readPassword("aB3$xY9!").strength, "almost", "eight mixed characters");
    assert.equal(readPassword(`${randomLetters(10)} ${randomLetters(10)}`).strength, "strong", "a long lowercase phrase");
    assert.ok(readPassword(randomLetters(16)).bits > readPassword("aB3$xY9!").bits);
  });

  test("below the server minimum is weak whatever its characters", () => {
    assert.equal(readPassword("x9$Q!").strength, "weak");
    assert.equal(readPassword("x9$Q!").longEnough, false);
  });
});

async function mount(autoComplete: "new-password" | "current-password" = "new-password") {
  const { PasswordField } = await import("@/components/ui/FormField");
  function Harness() {
    const [value, setValue] = useState("");
    return <PasswordField id="pw" label="Contraseña nueva" autoComplete={autoComplete} value={value} onChange={(event) => setValue(event.target.value)} />;
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>));
  const input = host.querySelector<HTMLInputElement>("#pw") as HTMLInputElement;
  const type = (value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const coach = () => host.querySelector<HTMLElement>('[data-testid="password-coach"]');
  const ticks = () => [...(coach()?.querySelectorAll("li") ?? [])].map((item) => item.getAttribute("data-met"));
  return { host, input, type, coach, ticks, close: () => act(async () => root.unmount()) };
}

describe("the password field coaches a new password", () => {
  test("the meter names weak, almost and strong in plain words as the person types", async () => {
    const field = await mount();
    try {
      assert.equal(field.coach()?.dataset.strength, "empty");
      await field.type("Password0");
      assert.equal(field.coach()?.dataset.strength, "weak");
      assert.match(field.coach()?.textContent ?? "", /Seguridad: Débil/);
      await field.type("aB3$xY9!");
      assert.match(field.coach()?.textContent ?? "", /Seguridad: Casi lista/);
      await field.type(`${randomLetters(10)} ${randomLetters(10)}`);
      assert.match(field.coach()?.textContent ?? "", /Seguridad: Fuerte/);
    } finally {
      await field.close();
    }
  });

  test("the checklist ticks live while typing, and coaching is never an error", async () => {
    const field = await mount();
    try {
      assert.deepEqual(field.ticks(), ["false", "false"]);
      await field.type("abc");
      assert.deepEqual(field.ticks(), ["false", "false"], "a run is not ticked");
      await field.type(randomLetters(8));
      assert.deepEqual(field.ticks(), ["true", "true"], "ticked before any button press");
      await field.type("abc");
      assert.equal(field.input.getAttribute("aria-invalid"), null);
      assert.ok(field.input.getAttribute("aria-describedby")?.split(" ").includes("pw-coach"));
    } finally {
      await field.close();
    }
  });

  test("paste is never blocked, and managers get autocomplete and the server's rules", async () => {
    const field = await mount();
    try {
      const paste = new Event("paste", { bubbles: true, cancelable: true });
      field.input.dispatchEvent(paste);
      assert.equal(paste.defaultPrevented, false);
      const pasted = `${randomLetters(8)}-${randomLetters(8)}`;
      await field.type(pasted);
      assert.equal(field.input.value, pasted);
      assert.equal(field.input.autocomplete, "new-password");
      assert.equal(field.input.getAttribute("passwordrules"), `minlength: ${PASSWORD_MIN_LENGTH};`);
    } finally {
      await field.close();
    }
  });

  test("a current password has the eye but no meter and no generator rules", async () => {
    const field = await mount("current-password");
    try {
      assert.equal(field.coach(), null);
      assert.equal(field.input.getAttribute("passwordrules"), null);
      assert.ok(field.host.querySelector('button[aria-controls="pw"]'));
    } finally {
      await field.close();
    }
  });
});
