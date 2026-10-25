import assert from "node:assert/strict";
import { beforeAll, afterAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { IdentityAppearance } from "@/lib/identity-appearance";
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());
async function mount(
  saved: IdentityAppearance,
  onSave: (value: IdentityAppearance) => void,
) {
  const { act } = await import("react"),
    { createRoot } = await import("react-dom/client"),
    { I18nextProvider } = await import("react-i18next"),
    i18next = (await import("i18next")).default,
    copy = (await import("@/public/locales/es-419/common.json")).default,
    Editor = (await import("@/components/identity/IdentityEditor")).default;
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    resources: { "es-419": { translation: copy } },
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () =>
    root.render(
      <I18nextProvider i18n={i18n}>
        <Editor saved={saved} name="La Palma" business onSave={onSave} />
      </I18nextProvider>,
    ),
  );
  return {
    act,
    host,
    root,
    button: (name: string) =>
      [...host.querySelectorAll<HTMLButtonElement>("button")].find(
        (button) =>
          button.textContent === name ||
          button.getAttribute("aria-label") === name,
      )!,
  };
}
test("avatar edits stay drafts until save and failed save preserves the edit", async () => {
  const saved: IdentityAppearance = { kind: "default" },
    writes: IdentityAppearance[] = [];
  let fail = true;
  const page = await mount(saved, (value) => {
    if (fail) throw new Error("quota");
    writes.push(value);
  });
  try {
    const swatch =
      page.host.querySelectorAll<HTMLButtonElement>("fieldset button")[2];
    await page.act(async () => swatch.click());
    assert.equal(writes.length, 0);
    await page.act(async () => page.button("Guardar imagen").click());
    assert.ok(page.host.querySelector('[role="alert"]'));
    assert.equal(page.button("Guardar imagen").disabled, false);
    fail = false;
    await page.act(async () => page.button("Guardar imagen").click());
    assert.equal(writes[0].kind, "avatar");
    assert.deepEqual(saved, { kind: "default" });
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("discarding the editor leaves saved identity unchanged", async () => {
  const saved: IdentityAppearance = {
    kind: "avatar",
    token: "teal",
    mark: "initials",
  };
  const writes: IdentityAppearance[] = [];
  const page = await mount(saved, (value) => writes.push(value));
  await page.act(async () => page.button("Ícono predeterminado").click());
  await page.act(async () => page.root.unmount());
  page.host.remove();
  assert.deepEqual(writes, []);
  assert.equal(saved.kind, "avatar");
});
test("removing an image is a draft until explicit save", async () => {
  const saved: IdentityAppearance = {
      kind: "image",
      source: "data:image/png;base64,YQ==",
      rendered: "data:image/png;base64,YQ==",
      width: 10,
      height: 10,
      crop: { mode: "fit", zoom: 1, x: 0, y: 0 },
    },
    writes: IdentityAppearance[] = [];
  const page = await mount(saved, (value) => writes.push(value));
  try {
    await page.act(async () => page.button("Quitar imagen").click());
    assert.equal(writes.length, 0);
    await page.act(async () => page.button("Guardar imagen").click());
    assert.deepEqual(writes, [{ kind: "default" }]);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("unsupported file leaves the current image draft intact", async () => {
  const saved: IdentityAppearance = {
      kind: "image",
      source: "data:image/png;base64,YQ==",
      rendered: "data:image/png;base64,YQ==",
      width: 10,
      height: 10,
      crop: { mode: "fit", zoom: 1, x: 0, y: 0 },
    },
    writes: IdentityAppearance[] = [];
  const page = await mount(saved, (value) => writes.push(value));
  try {
    const input =
      page.host.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [new File(["<svg/>"], "unsafe.svg", { type: "image/svg+xml" })],
    });
    await page.act(async () =>
      input.dispatchEvent(new Event("change", { bubbles: true })),
    );
    assert.match(
      page.host.querySelector('[role="alert"]')?.textContent ?? "",
      /JPG, PNG o WebP/,
    );
    assert.ok(page.button("Quitar imagen"));
    assert.deepEqual(writes, []);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("file decoding uses CSP-safe data bytes and bounds the saved source", async () => {
  const { loadIdentityImage } = await import("@/lib/identity-appearance");
  const OriginalImage = globalThis.Image,
    originalContext = HTMLCanvasElement.prototype.getContext,
    originalData = HTMLCanvasElement.prototype.toDataURL;
  let decodedSource = "",
    drawn = false;
  class DecodedImage {
    naturalWidth = 2560;
    naturalHeight = 1280;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(value: string) {
      decodedSource = value;
      queueMicrotask(() => this.onload?.());
    }
  }
  globalThis.Image = DecodedImage as unknown as typeof Image;
  HTMLCanvasElement.prototype.getContext = (() => ({
    drawImage: () => {
      drawn = true;
    },
  })) as unknown as typeof originalContext;
  HTMLCanvasElement.prototype.toDataURL = () => "data:image/webp;base64,YQ==";
  try {
    const image = await loadIdentityImage(
      new File(["image bytes"], "logo.png", { type: "image/png" }),
    );
    assert.match(decodedSource, /^data:image\/png;base64,/);
    assert.equal(image.width, 1280);
    assert.equal(image.height, 640);
    assert.equal(drawn, true);
  } finally {
    globalThis.Image = OriginalImage;
    HTMLCanvasElement.prototype.getContext = originalContext;
    HTMLCanvasElement.prototype.toDataURL = originalData;
  }
});
