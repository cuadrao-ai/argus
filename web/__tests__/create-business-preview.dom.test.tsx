import assert from "node:assert/strict";
import { beforeAll, afterAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());
async function mount() {
  const { act } = await import("react"),
    { createRoot } = await import("react-dom/client"),
    { I18nextProvider } = await import("react-i18next"),
    i18next = (await import("i18next")).default,
    copy = (await import("@/public/locales/es-419/common.json")).default,
    Create = (await import("@/app/design-workspace/CreateBusinessPreview"))
      .default;
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    resources: { "es-419": { translation: copy } },
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host),
    created: unknown[] = [];
  await act(async () =>
    root.render(
      <I18nextProvider i18n={i18n}>
        <Create
          onClose={() => undefined}
          onCreated={(value) => created.push(value)}
        />
      </I18nextProvider>,
    ),
  );
  return {
    act,
    root,
    host,
    created,
    change: async (input: HTMLInputElement, value: string) =>
      act(async () => {
        Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          "value",
        )!.set!.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }),
  };
}
test("creation validates required fields, restores drafts, and creates only after explicit submit", async () => {
  localStorage.clear();
  let page = await mount();
  try {
    await page.act(async () =>
      document
        .querySelector("form")!
        .dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        ),
    );
    const name = document.querySelector<HTMLInputElement>(
      'input[autocomplete="organization"]',
    )!;
    assert.equal(name.getAttribute("aria-invalid"), "true");
    assert.equal(page.created.length, 0);
    await page.change(name, "Nuevo Taller");
    await page.act(async () => page.root.unmount());
    page.host.remove();
    page = await mount();
    assert.equal(
      document.querySelector<HTMLInputElement>(
        'input[autocomplete="organization"]',
      )!.value,
      "Nuevo Taller",
    );
    assert.match(
      document.querySelector('[role="combobox"]')?.textContent ?? "",
      /Selecciona/,
    );
    await page.act(async () =>
      (
        document.querySelector('[role="combobox"]') as HTMLButtonElement
      ).click(),
    );
    const canada = [
      ...document.querySelectorAll<HTMLButtonElement>('[role="option"]'),
    ].find((option) => option.textContent?.includes("Canadá"))!;
    await page.act(async () => canada.click());
    const form = document.querySelector("form")!;
    await page.act(async () => {
      form.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      form.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });
    assert.equal(page.created.length, 1);
    assert.equal((page.created[0] as { country: string }).country, "CA");
    assert.equal(localStorage.getItem("cuadrao-new-business-draft-v1"), null);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
    localStorage.clear();
  }
});
