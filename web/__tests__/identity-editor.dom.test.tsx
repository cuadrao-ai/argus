import assert from "node:assert/strict";
import { beforeAll, afterAll, test } from "bun:test";
import type { ComponentProps, ReactNode } from "react";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { IdentityAppearance, IdentityCrop } from "@/lib/identity-appearance";
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());
async function mountNode(node: ReactNode) {
  const { act } = await import("react"),
    { createRoot } = await import("react-dom/client"),
    { I18nextProvider } = await import("react-i18next"),
    i18next = (await import("i18next")).default,
    copy = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    resources: { "es-419": { translation: copy } },
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () =>
    root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>),
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
    radio: (name: string) =>
      host.querySelector<HTMLInputElement>(
        `input[type="radio"][aria-label="${name}"]`,
      )!,
    checked: () =>
      [...host.querySelectorAll<HTMLInputElement>('input[type="radio"]')]
        .filter((radio) => radio.checked)
        .map((radio) => radio.getAttribute("aria-label")),
    preview: () => host.querySelector<HTMLElement>('[data-testid="identity-preview"]')!,
    uploadTile: () => host.querySelector<HTMLButtonElement>('[data-testid="identity-upload"]')!,
  };
}
async function mount(
  saved: IdentityAppearance,
  onSave: (value: IdentityAppearance) => void | Promise<void>,
  business = true,
) {
  const Editor = (await import("@/components/identity/IdentityEditor")).default;
  return mountNode(
    <Editor saved={saved} name="La Palma" business={business} onSave={onSave} />,
  );
}
function stubImageDecoder(naturalWidth: number, naturalHeight: number) {
  const OriginalImage = globalThis.Image,
    originalContext = HTMLCanvasElement.prototype.getContext,
    originalData = HTMLCanvasElement.prototype.toDataURL;
  const decoded = { source: "", drawn: false };
  class DecodedImage {
    naturalWidth = naturalWidth;
    naturalHeight = naturalHeight;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(value: string) {
      decoded.source = value;
      queueMicrotask(() => this.onload?.());
    }
  }
  globalThis.Image = DecodedImage as unknown as typeof Image;
  HTMLCanvasElement.prototype.getContext = (() => ({
    drawImage: () => {
      decoded.drawn = true;
    },
  })) as unknown as typeof originalContext;
  HTMLCanvasElement.prototype.toDataURL = () => "data:image/webp;base64,YQ==";
  return {
    decoded,
    restore: () => {
      globalThis.Image = OriginalImage;
      HTMLCanvasElement.prototype.getContext = originalContext;
      HTMLCanvasElement.prototype.toDataURL = originalData;
    },
  };
}
const logo = () => new File(["image bytes"], "logo.png", { type: "image/png" });
function pick(page: Awaited<ReturnType<typeof mount>>, file: File) {
  const input = page.host.querySelector<HTMLInputElement>('input[type="file"]')!;
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  return page.act(async () => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
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
    await page.act(async () =>
      page.host.querySelectorAll<HTMLInputElement>('input[type="radio"]')[2].click(),
    );
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
  await page.act(async () => page.radio("Ícono predeterminado").click());
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
  const stub = stubImageDecoder(2560, 1280);
  try {
    const image = await loadIdentityImage(logo());
    assert.match(stub.decoded.source, /^data:image\/png;base64,/);
    assert.equal(image.width, 1280);
    assert.equal(image.height, 640);
    assert.equal(stub.decoded.drawn, true);
  } finally {
    stub.restore();
  }
});


test("an explicit default identity overrides the prior avatar and stays selected on reopen", async () => {
  const previousEnv = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { SavedIdentityMark, useIdentityAppearance } = await import("@/components/identity/IdentityMark");
  const { identityKey, saveAppearance, IDENTITY_EVENT } = await import("@/lib/identity-appearance");
  const scope = "person:default-regression";
  let stored: IdentityAppearance | null = null;
  function Probe() {
    stored = useIdentityAppearance(scope);
    return <SavedIdentityMark scope={scope} fallback={<span>Prior avatar</span>} />;
  }
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<Probe />));
    assert.equal(host.textContent, "Prior avatar");
    assert.equal(stored, null);
    await act(async () => {
      saveAppearance(localStorage, scope, { kind: "default" });
      window.dispatchEvent(new Event(IDENTITY_EVENT));
    });
    assert.equal(host.textContent, "", "saved default must replace the old avatar");
    assert.ok(host.querySelector("svg"));
    await act(async () => root.render(<Probe key="reopened" />));
    assert.deepEqual(stored, { kind: "default" });
    assert.equal(host.textContent, "");
    Object.assign(process.env, { NODE_ENV: "production" });
    await act(async () => root.render(<Probe key="production" />));
    assert.equal(host.textContent, "Prior avatar", "production ignores local overrides");
  } finally {
    await act(async () => root.unmount());
    host.remove();
    localStorage.removeItem(identityKey(scope));
    Object.assign(process.env, previousEnv);
  }
});

test("one screen shows every choice with one selected and save off until a change", async () => {
  const page = await mount({ kind: "default" }, () => {});
  try {
    assert.equal(page.host.querySelector('[role="tablist"], [role="tab"]'), null);
    assert.ok(page.host.querySelector('[role="radiogroup"][aria-label="Cambiar imagen"]'));
    assert.ok(page.button("Elegir imagen"));
    assert.deepEqual(page.checked(), ["Ícono predeterminado"]);
    assert.equal(page.host.querySelectorAll('input[type="radio"]').length, 7);
    assert.doesNotMatch(page.host.textContent ?? "", /10 MB/);
    assert.equal(page.button("Guardar imagen").disabled, true);
    assert.equal(page.button("Quitar imagen"), undefined);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("the personal editor keeps its photo words and round preview", async () => {
  const page = await mount({ kind: "default" }, () => {}, false);
  try {
    assert.ok(page.button("Elegir foto"));
    assert.ok(page.button("Guardar foto"));
    assert.match(page.preview().className, /rounded-full/);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("a chosen color previews its initials, also when saved with the briefcase", async () => {
  const page = await mount({ kind: "avatar", token: "teal", mark: "icon" }, () => {});
  try {
    assert.equal(page.preview().textContent, "LP");
    assert.equal(page.checked().length, 1);
    assert.equal(page.button("Guardar imagen").disabled, false);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("a picked file fills the upload tile instead of adding a ninth tile", async () => {
  const writes: IdentityAppearance[] = [];
  const page = await mount({ kind: "default" }, (value) => writes.push(value));
  const stub = stubImageDecoder(400, 200);
  try {
    await pick(page, logo());
    assert.equal(page.host.querySelectorAll('input[type="radio"]').length, 7);
    assert.deepEqual(page.checked(), []);
    assert.equal(page.uploadTile().getAttribute("aria-pressed"), "true");
    assert.ok(page.uploadTile().querySelector("img"));
    assert.ok(page.preview().querySelector("img"));
    assert.ok(page.button("Quitar imagen"));
    await page.act(async () => page.button("Guardar imagen").click());
    assert.equal(writes[0].kind, "image");
    assert.deepEqual(writes[0].kind === "image" && writes[0].crop, { mode: "fit", zoom: 1, x: 0, y: 0 });
  } finally {
    stub.restore();
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("the filled tile selects the image first and replaces it once selected", async () => {
  const page = await mount({ kind: "default" }, () => {});
  const stub = stubImageDecoder(400, 200);
  const input = page.host.querySelector<HTMLInputElement>('input[type="file"]')!;
  let opened = 0;
  input.click = () => {
    opened += 1;
  };
  try {
    await pick(page, logo());
    await page.act(async () => page.radio("Ícono predeterminado").click());
    assert.equal(page.uploadTile().getAttribute("aria-pressed"), "false");
    assert.equal(page.uploadTile().getAttribute("aria-label"), "Imagen");
    assert.ok(page.uploadTile().querySelector("img"));
    await page.act(async () => page.uploadTile().click());
    assert.equal(opened, 0);
    assert.equal(page.uploadTile().getAttribute("aria-pressed"), "true");
    assert.equal(page.uploadTile().getAttribute("aria-label"), "Elegir imagen");
    assert.deepEqual(page.checked(), []);
    await page.act(async () => page.uploadTile().click());
    assert.equal(opened, 1);
  } finally {
    stub.restore();
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("a saved old neutral color still previews with no tile checked", async () => {
  const page = await mount({ kind: "avatar", token: "ocean", mark: "initials" }, () => {});
  try {
    assert.equal(page.preview().textContent, "LP");
    assert.deepEqual(page.checked(), []);
    assert.equal(page.button("Guardar imagen").disabled, true);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("dropping a file on the preview selects it", async () => {
  const page = await mount({ kind: "default" }, () => {});
  const stub = stubImageDecoder(200, 400);
  try {
    const drop = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(drop, "dataTransfer", { value: { files: [logo()] } });
    await page.act(async () => {
      page.preview().dispatchEvent(drop);
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    assert.equal(page.uploadTile().getAttribute("aria-pressed"), "true");
  } finally {
    stub.restore();
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("every tile carries the one border token and the empty upload tile stays dashed", async () => {
  const page = await mount({ kind: "default" }, () => {});
  const stub = stubImageDecoder(400, 200);
  const border = "border-[var(--segment-thumb-border)]";
  try {
    const tiles = () => [
      page.uploadTile(),
      ...page.host.querySelectorAll<HTMLElement>('[role="radiogroup"] label'),
    ];
    assert.equal(tiles().length, 8);
    for (const tile of tiles()) assert.ok(tile.classList.contains(border), tile.className);
    assert.ok(page.uploadTile().classList.contains("border-dashed"));
    await pick(page, logo());
    assert.ok(page.uploadTile().classList.contains(border));
    assert.equal(page.uploadTile().classList.contains("border-dashed"), false);
  } finally {
    stub.restore();
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("the selected filled tile shows its replace icon where there is no hover", async () => {
  const page = await mount({ kind: "default" }, () => {});
  const stub = stubImageDecoder(400, 200);
  const cue = () => page.uploadTile().querySelector("span.absolute");
  try {
    assert.equal(cue(), null);
    await pick(page, logo());
    assert.ok(cue(), "the icon is on the tile");
    assert.equal(cue()?.classList.contains("opacity-0"), false, "only a device with hover may hide it");
    await page.act(async () => page.radio("Ícono predeterminado").click());
    assert.equal(cue(), null, "a tap on an unselected tile selects, it does not replace");
  } finally {
    stub.restore();
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("Quitar imagen waits for a save in flight", async () => {
  let finish = () => {};
  const page = await mount(
    { kind: "default" },
    () => new Promise<void>((resolve) => { finish = resolve; }),
  );
  const stub = stubImageDecoder(400, 200);
  try {
    await pick(page, logo());
    await page.act(async () => page.button("Guardar imagen").click());
    assert.equal(page.button("Quitar imagen").disabled, true);
    await page.act(async () => finish());
    assert.equal(page.button("Quitar imagen").disabled, false);
  } finally {
    stub.restore();
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});
test("every color in the profile picker carries the tile border", async () => {
  const Dialog = (await import("@/components/sidebar/ProfileDetailsDialog")).default;
  const { createRef } = await import("react");
  const stub = () => {};
  const props = {
    profile: { id: "person-1", display_name: "Ana Peña", email: "ana@example.test", avatar_theme: "plum" },
    accountKind: "registered",
    closeProfileModal: stub,
    onEscape: stub,
    returnFocusRef: createRef(),
    avatarClassName: "",
    avatarTriggerRef: createRef(),
    avatarThemeDrawerRef: createRef(),
    isAvatarPickerOpen: true,
    toggleAvatarPicker: stub,
    closeAvatarPicker: stub,
    handleAvatarThemeSelect: stub,
    handleAvatarThemeKeyDown: stub,
    languagePickerRef: createRef(),
    setIsLanguagePickerOpen: stub,
    currentLanguage: "es-419",
    currentLanguageAbbreviation: "es",
    handleLanguageSelect: stub,
  } as unknown as ComponentProps<typeof Dialog>;
  const page = await mountNode(<Dialog {...props} />);
  try {
    const chips = [...document.querySelectorAll('[role="radio"] > span')];
    assert.equal(chips.length, 7);
    for (const chip of chips)
      assert.ok(chip.classList.contains("border-[var(--segment-thumb-border)]"), chip.className);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
  }
});

const SPACE = "6038d05e-0000-4000-8000-000000000001";
const STORED_CROP = { mode: "fill", zoom: 2, x: 0.25, y: -0.5 } as const;
type ServerAppearance =
  | Exclude<IdentityAppearance, { kind: "image" }>
  | { kind: "image"; asset_id: string; crop: IdentityCrop };
/** The profile endpoints as the Negocio screen calls them, kept in memory. */
function profileServer(initial: ServerAppearance = { kind: "default" }) {
  const state = {
    appearance: initial,
    revision: 1,
    uploads: 0,
    patches: [] as ServerAppearance[],
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const path = String(url);
    if (path.startsWith("data:") || path.endsWith(".webp"))
      return new Response(new Blob(["image bytes"], { type: "image/webp" }));
    if (path.endsWith("/appearance/assets")) {
      state.uploads += 1;
      return Response.json({ asset_id: "asset-1" });
    }
    if (init?.method === "PATCH") {
      state.appearance = JSON.parse(String(init.body)).appearance;
      state.patches.push(state.appearance);
      state.revision += 1;
    }
    return Response.json({
      space_id: SPACE,
      name: "La Palma",
      country: "DO",
      currency: "DOP",
      revision: state.revision,
      details: {},
      appearance: state.appearance,
      image:
        state.appearance.kind === "image"
          ? {
              asset_id: state.appearance.asset_id,
              width: 400,
              height: 200,
              source_url: "http://localhost/source.webp",
              rendered_url: "http://localhost/rendered.webp",
            }
          : null,
    });
  }) as typeof fetch;
  return { state, restore: () => { globalThis.fetch = originalFetch; } };
}
/** The Negocio wiring: the editor opens once the saved value is ready, and it starts from what the server last returned. */
async function mountLive() {
  const { useState, useSyncExternalStore } = await import("react");
  const { businessAppearanceState, subscribeBusinessAppearance } = await import("@/lib/business-profile-api");
  const { useBusinessProfile } = await import("@/components/business-app/useBusinessProfile");
  const { useIdentityAppearance } = await import("@/components/identity/IdentityMark");
  const Editor = (await import("@/components/identity/IdentityEditor")).default;
  function Live() {
    const server = useBusinessProfile(SPACE, true, () => {});
    const saved = useIdentityAppearance(`business:${SPACE}`);
    const state = useSyncExternalStore(subscribeBusinessAppearance, () => businessAppearanceState(SPACE));
    const [opened, setOpened] = useState(0);
    if (!saved || state !== "ready") return null;
    return (
      <Editor
        key={opened}
        saved={saved}
        name="La Palma"
        business
        onSave={async (value) => {
          await server.saveAppearance(value);
          setOpened((count) => count + 1);
        }}
      />
    );
  }
  const page = await mountNode(<Live />);
  await settle(page);
  return page;
}
const settle = (page: { act: typeof import("react").act }) =>
  page.act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
async function liveTest(
  initial: ServerAppearance | undefined,
  run: (
    page: Awaited<ReturnType<typeof mountLive>>,
    server: ReturnType<typeof profileServer>,
  ) => Promise<void>,
) {
  const previous = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const server = profileServer(initial);
  const stub = stubImageDecoder(400, 200);
  const page = await mountLive();
  try {
    await run(page, server);
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
    (await import("@/lib/business-profile-api")).clearBusinessAppearance(SPACE);
    stub.restore();
    server.restore();
    if (previous === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = previous;
  }
}
test("a color saves its old token through the live profile and reopens selected", async () => {
  await liveTest(undefined, async (page, server) => {
    await page.act(async () => page.radio("Morera").click());
    await page.act(async () => page.button("Guardar imagen").click());
    await settle(page);
    assert.deepEqual(server.state.patches, [{ kind: "avatar", token: "plum", mark: "initials" }]);
    assert.deepEqual(page.checked(), ["Morera"]);
    assert.equal(page.preview().textContent, "LP");
    assert.equal(page.button("Guardar imagen").disabled, true);
  });
});
test("a new file uploads once, saves the centered crop, reopens filled, and Quitar imagen clears it", async () => {
  await liveTest(undefined, async (page, server) => {
    await pick(page, logo());
    await page.act(async () => page.button("Guardar imagen").click());
    await settle(page);
    assert.equal(server.state.uploads, 1);
    assert.deepEqual(server.state.patches, [
      { kind: "image", asset_id: "asset-1", crop: { mode: "fit", zoom: 1, x: 0, y: 0 } },
    ]);
    assert.equal(page.uploadTile().getAttribute("aria-pressed"), "true");
    assert.ok(page.uploadTile().querySelector("img"));
    assert.equal(page.button("Guardar imagen").disabled, true);
    await page.act(async () => page.button("Quitar imagen").click());
    await page.act(async () => page.button("Guardar imagen").click());
    await settle(page);
    assert.deepEqual(server.state.patches.at(-1), { kind: "default" });
    assert.deepEqual(page.checked(), ["Ícono predeterminado"]);
    assert.equal(page.uploadTile().querySelector("img"), null);
    assert.equal(page.button("Quitar imagen"), undefined);
    assert.equal(server.state.uploads, 1);
  });
});
test("a saved image keeps its stored crop: reopening, a wrong file and a color change write nothing", async () => {
  const saved = { kind: "image", asset_id: "asset-1", crop: STORED_CROP } as const;
  await liveTest(saved, async (page, server) => {
    assert.equal(page.uploadTile().getAttribute("aria-pressed"), "true");
    assert.ok(page.preview().querySelector("img"));
    assert.equal(page.button("Guardar imagen").disabled, true);
    await pick(page, new File(["<svg/>"], "unsafe.svg", { type: "image/svg+xml" }));
    assert.match(page.host.querySelector('[role="alert"]')?.textContent ?? "", /JPG, PNG o WebP/);
    assert.equal(page.button("Guardar imagen").disabled, true);
    await page.act(async () => page.radio("Laguna").click());
    assert.equal(page.button("Guardar imagen").disabled, false);
    await page.act(async () => page.uploadTile().click());
    assert.equal(page.button("Guardar imagen").disabled, true);
    assert.deepEqual(server.state.patches, []);
    assert.equal(server.state.uploads, 0);
    assert.deepEqual(server.state.appearance, saved);
  });
});
