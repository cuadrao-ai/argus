import { afterAll, beforeAll, expect, test } from "bun:test";
import type { ReactNode } from "react";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(node: ReactNode, lng: "en" | "es-419" = "en") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const i18n = i18next.createInstance();
  await i18n.init({
    lng,
    resources: { en: { translation: en }, "es-419": { translation: es } },
    interpolation: { escapeValue: false },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);
  });
  return {
    host,
    async unmount() {
      await act(async () => root.unmount());
      host.remove();
    },
  };
}

test("a label click toggles the signup checkbox and the row is at least 44px tall", async () => {
  const { default: AuthForm } = await import("../components/auth/AuthForm");
  const submissions: string[] = [];
  const view = await mount(
    <AuthForm
      mode="signup"
      onSubmit={async (submission) => {
        submissions.push(submission.ageConfirmedAt ?? "");
      }}
    />,
  );
  const label = view.host.querySelector("label");
  const checkbox = view.host.querySelector("#age-confirmation-checkbox");
  const submit = view.host.querySelector("button[type='submit']");
  expect(label).toBeInstanceOf(HTMLLabelElement);
  expect(checkbox).toBeInstanceOf(HTMLInputElement);
  expect(submit).toBeInstanceOf(HTMLButtonElement);
  expect((submit as HTMLButtonElement).disabled).toBe(true);
  expect(Number.parseFloat(getComputedStyle(label!).minHeight)).toBeGreaterThanOrEqual(44);
  expect(view.host.textContent).toContain(en.auth.age_confirmation.checkbox);
  expect(view.host.textContent).not.toContain("You confirmed you're 18 or older.");
  const { act } = await import("react");
  await act(async () => {
    label?.querySelector("span")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect((checkbox as HTMLInputElement).checked).toBe(true);
  expect((submit as HTMLButtonElement).disabled).toBe(false);
  expect(window.localStorage.getItem("cuadrao-age-confirmed-at")).toBeNull();
  await act(async () => {
    view.host.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  expect(window.localStorage.getItem("cuadrao-age-confirmed-at")).toBeNull();
  await view.unmount();
});

test("signup without the checkbox shows the missing message and does not submit", async () => {
  const { default: AuthForm } = await import("../components/auth/AuthForm");
  const submissions: number[] = [];
  const view = await mount(
    <AuthForm
      mode="signup"
      onSubmit={async () => {
        submissions.push(1);
      }}
    />,
    "es-419",
  );
  const { act } = await import("react");
  await act(async () => {
    view.host.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(submissions).toEqual([]);
  expect(view.host.textContent).toContain(es.auth.age_confirmation.missing);
  expect(view.host.textContent).toContain(es.auth.age_confirmation.checkbox);
  await view.unmount();
});
