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

test("signup shows no age checkbox and submits without an age field", async () => {
  const { default: AuthForm } = await import("../components/auth/AuthForm");
  const submissions: Record<string, unknown>[] = [];
  const view = await mount(
    <AuthForm
      mode="signup"
      onSubmit={async (submission) => {
        submissions.push({ ...submission });
      }}
    />,
    "es-419",
  );
  const submit = view.host.querySelector("button[type='submit']");
  expect(view.host.querySelector("input[type='checkbox']")).toBeNull();
  expect(view.host.textContent).not.toContain("18");
  expect(submit).toBeInstanceOf(HTMLButtonElement);
  expect((submit as HTMLButtonElement).disabled).toBe(false);
  const { act } = await import("react");
  for (const [selector, value] of [
    ['input[type="email"]', "synthetic@example.test"],
    ['input[autocomplete="new-password"]', "synthetic long password 47"],
  ]) {
    const input = view.host.querySelector<HTMLInputElement>(selector)!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }
  await act(async () => {
    view.host.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).not.toHaveProperty("ageConfirmedAt");
  expect(view.host.querySelector("[role='alert']")).toBeNull();
  await view.unmount();
});
