import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/form" });
  document.body.innerHTML = "";
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const HINT = "Nueve dígitos.";
const TOO_SHORT = "Un RNC tiene 9 dígitos.";
const REQUIRED = "Escribe el nombre.";

async function mount() {
  const { ErrorSummary, FormField, PasswordField, useFieldChecks } = await import("@/components/ui/FormField");
  const sent: Record<string, string>[] = [];
  function Harness() {
    const [values, setValues] = useState({ name: "", code: "", secret: "" });
    const checks = useFieldChecks(
      {
        name: (all) => (all.name.trim() ? null : REQUIRED),
        code: (all) => (all.code.length === 9 ? null : TOO_SHORT),
        secret: () => null,
      },
      values,
    );
    const ids = { name: "ff-name", code: "ff-code", secret: "ff-secret" } as const;
    const labels = { name: "Nombre", code: "RNC", secret: "Clave" } as const;
    return (
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (checks.submit()) sent.push(values);
        }}
      >
        <ErrorSummary
          key={checks.attempt}
          title="Revisa estos campos para seguir:"
          items={checks.summary.map((field) => ({ id: ids[field], label: labels[field] }))}
        />
        <FormField id={ids.name} label="Nombre" error={checks.errorOf("name")} value={values.name} onBlur={() => checks.blur("name")} onChange={(event) => setValues({ ...values, name: event.target.value })} />
        <FormField id={ids.code} label="RNC" hint={HINT} inputMode="numeric" error={checks.errorOf("code")} value={values.code} onBlur={() => checks.blur("code")} onChange={(event) => setValues({ ...values, code: event.target.value })} />
        <PasswordField id={ids.secret} label="Clave" autoComplete="new-password" value={values.secret} onChange={(event) => setValues({ ...values, secret: event.target.value })} />
        <button type="submit">Guardar</button>
      </form>
    );
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  let root: Root | null = null;
  await act(async () => {
    root = createRoot(host);
    root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>);
  });
  const field = (id: string) => host.querySelector<HTMLInputElement>(`#ff-${id}`) as HTMLInputElement;
  const note = (id: string) => host.querySelector<HTMLElement>(`#ff-${id}-note`);
  const type = async (id: string, value: string) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    assert.ok(setter);
    await act(async () => {
      setter.call(field(id), value);
      field(id).dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const leave = (id: string) => act(async () => {
    field(id).focus();
    field(id).blur();
  });
  const submit = () => act(async () => {
    host.querySelector<HTMLButtonElement>('button[type="submit"]')?.click();
  });
  return { host, sent, field, note, type, leave, submit, close: () => act(async () => root?.unmount()) };
}

const digits = (count: number) => Array.from({ length: count }, () => String(1 + Math.floor(Math.random() * 9))).join("");

describe("the shared form field", () => {
  test("a field stays quiet while typing, shows its error on leaving, then rechecks every keystroke", async () => {
    const form = await mount();
    try {
      await form.type("code", digits(4));
      assert.equal(form.field("code").getAttribute("aria-invalid"), null, "no red on the first keystrokes");
      assert.equal(form.note("code")?.textContent, HINT);

      await form.leave("code");
      assert.equal(form.field("code").getAttribute("aria-invalid"), "true");
      assert.equal(form.note("code")?.textContent, TOO_SHORT, "the error replaces the hint");
      assert.equal(form.field("code").getAttribute("aria-describedby"), "ff-code-note");

      await form.type("code", digits(5));
      assert.equal(form.note("code")?.textContent, TOO_SHORT, "still wrong, still shown, without leaving");
      await form.type("code", digits(9));
      assert.equal(form.field("code").getAttribute("aria-invalid"), null, "fixed on this keystroke");
      assert.equal(form.note("code")?.textContent, HINT);
    } finally {
      await form.close();
    }
  });

  test("leaving an empty field says nothing; the submit catches it", async () => {
    const form = await mount();
    try {
      await form.leave("name");
      assert.equal(form.note("name")?.textContent, "");
      assert.equal(form.field("name").getAttribute("aria-invalid"), null);
    } finally {
      await form.close();
    }
  });

  test("the hint and the error share one reserved line, so the submit keeps its place", async () => {
    const form = await mount();
    try {
      const line = form.note("code");
      const blocks = () => [...(form.host.querySelector("form")?.children ?? [])];
      const before = blocks();
      await form.type("code", digits(3));
      await form.leave("code");
      assert.equal(form.note("code")?.textContent, TOO_SHORT);
      assert.equal(form.note("code"), line, "the error fills the same line");
      assert.deepEqual(blocks(), before, "nothing joins the form between the field and the submit");
      assert.match(line?.className ?? "", /min-h-\[22px\]/);
      assert.ok(form.note("name"), "a field without a hint still reserves its line");
    } finally {
      await form.close();
    }
  });

  test("a failed submit opens a summary that takes focus, and each link moves focus into its field", async () => {
    const form = await mount();
    try {
      await form.submit();
      assert.equal(form.sent.length, 0);
      const summary = form.host.querySelector<HTMLElement>('[data-testid="form-error-summary"]');
      assert.ok(summary);
      assert.equal(document.activeElement, summary);
      const links = [...summary.querySelectorAll<HTMLAnchorElement>("a")];
      assert.deepEqual(links.map((link) => link.textContent), ["Nombre", "RNC"]);
      // Two other test files replace HTMLAnchorElement.prototype.click for their downloads, so dispatch the click itself.
      await act(async () => { links[1].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })); });
      assert.equal(document.activeElement, form.field("code"));

      await form.type("name", "Colmado La Esquina");
      assert.deepEqual([...form.host.querySelectorAll('[data-testid="form-error-summary"] a')].map((link) => link.textContent), ["RNC"], "a fixed field leaves the summary");
      const code = digits(9);
      await form.type("code", code);
      assert.equal(form.host.querySelector('[data-testid="form-error-summary"]'), null);
      await form.submit();
      assert.equal(form.sent.length, 1);
      assert.equal(form.sent[0].code, code);
    } finally {
      await form.close();
    }
  });

  test("a code is text with a numeric keyboard, never a number input", async () => {
    const form = await mount();
    try {
      assert.equal(form.field("code").type, "text");
      assert.equal(form.field("code").inputMode, "numeric");
      const { FormField } = await import("@/components/ui/FormField");
      // @ts-expect-error a code or a postal code is not a quantity
      const refused = <FormField id="zip" label="Código postal" type="number" />;
      assert.ok(refused);
    } finally {
      await form.close();
    }
  });

  test("a password field shows and hides its value with a Spanish label", async () => {
    const form = await mount();
    try {
      const toggle = form.host.querySelector<HTMLButtonElement>('button[aria-controls="ff-secret"]');
      assert.ok(toggle);
      assert.equal(form.field("secret").type, "password");
      assert.equal(form.field("secret").autocomplete, "new-password");
      assert.equal(toggle.getAttribute("aria-label"), "Mostrar contraseña");
      await act(async () => toggle.click());
      assert.equal(form.field("secret").type, "text");
      assert.equal(toggle.getAttribute("aria-label"), "Ocultar contraseña");
    } finally {
      await form.close();
    }
  });
});
