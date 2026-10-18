import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { placeholderPhase, Settle, type SkeletonLayout } from "../components/business-app/business-skeletons";
import styles from "../components/business-app/business-skeletons.module.css";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(node: ReactNode, language = "es-419") {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { en: { translation: en }, "es-419": { translation: es } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = async (next: ReactNode) => {
    await act(async () => root.render(<I18nextProvider i18n={i18n}>{next}</I18nextProvider>));
  };
  await render(node);
  return { host, rerender: render, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

function visibleText(skeleton: Element): string {
  const clone = skeleton.cloneNode(true) as HTMLElement;
  clone.querySelectorAll(".sr-only").forEach((node) => node.remove());
  return clone.textContent ?? "";
}

describe("business skeletons", () => {
  test("placeholder phase stays blank until the delay and then shows the skeleton", () => {
    expect(placeholderPhase(299)).toBe("blank");
    expect(placeholderPhase(300)).toBe("skeleton");
  });

  test("a slow wait announces in the screen reader only, in Spanish and English", async () => {
    const view = await mount(<Settle pending layout="inbox" />);
    expect(view.host.querySelectorAll("[data-testid=business-loading]").length).toBe(0);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 250)); });
    expect(view.host.querySelectorAll("[data-testid=business-loading]").length).toBe(0);
    expect(view.host.textContent ?? "").not.toContain("Cargando");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 80)); });
    const skeleton = view.host.querySelector("[data-testid=business-loading]");
    expect(skeleton).not.toBeNull();
    expect(visibleText(skeleton as Element)).toBe("");
    expect(skeleton?.querySelector("[aria-hidden=true]")?.textContent).toBe("");
    expect(skeleton?.querySelector(".sr-only")?.textContent).toBe("Cargando");
    expect(skeleton?.textContent).not.toContain("Cargando...");
    expect(skeleton?.textContent).not.toContain("Cargando Cuadrao");
    expect(skeleton?.textContent).not.toContain("Cuadrando");
    await view.close();

    const english = await mount(<Settle pending layout="inbox" />, "en");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 320)); });
    expect(english.host.querySelector(".sr-only")?.textContent).toBe("Cargando");
    expect(english.host.textContent).not.toContain(en.common.loading);
    await english.close();
  });

  test("a fast resolve shows the content and never the skeleton", async () => {
    const view = await mount(<Settle pending layout="inbox" />);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 40)); });
    await view.rerender(<Settle pending={false} layout="inbox">Listo</Settle>);
    expect(view.host.textContent).toContain("Listo");
    expect(view.host.querySelectorAll("[data-testid=business-loading]").length).toBe(0);
    await view.close();
  });

  test("reduced motion turns the shimmer and the fade off in the stylesheet", async () => {
    const view = await mount(<Settle pending layout="rows" />);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 320)); });
    const shimmer = view.host.querySelector("[data-testid=business-skeleton-shimmer]");
    expect(shimmer?.className).toContain(styles.shimmer);
    const css = readFileSync(join(import.meta.dir, "../components/business-app/business-skeletons.module.css"), "utf8");
    const mediaAt = css.indexOf("@media (prefers-reduced-motion: reduce)");
    expect(mediaAt).toBeGreaterThanOrEqual(0);
    const region = css.slice(mediaAt);
    expect(region).toContain(".shimmer");
    expect(region).toContain(".fade");
    expect(region).toContain("animation: none");
    await view.close();
  });

  test("skeleton geometry keeps the loaded layout classes", async () => {
    const open = async (layout: SkeletonLayout) => {
      const view = await mount(<Settle pending layout={layout} />);
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 320)); });
      return view;
    };
    const overview = await open("overview");
    const grid = overview.host.querySelector('[data-layout="overview"] .grid');
    expect(grid?.children.length).toBe(3);
    expect(grid?.children[0]?.className).toContain("tablet:col-span-2");
    await overview.close();

    const detail = await open("detail");
    const markup = detail.host.querySelector('[data-layout="detail"]')?.innerHTML ?? "";
    expect(markup).toContain("desktop:min-h-[280px]");
    expect(markup).toContain("min-h-[200px]");
    expect(markup).toContain("desktop:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]");
    await detail.close();

    const inbox = await open("inbox");
    const row = inbox.host.querySelector('[data-layout="inbox"] .px-3');
    expect(row?.className).toContain("px-3");
    expect(row?.innerHTML).toContain("h-11");
    expect(row?.innerHTML).toContain("w-11");
    await inbox.close();
  });

  test("a second wait starts blank again", async () => {
    const view = await mount(<Settle pending layout="rows" />);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 320)); });
    expect(view.host.querySelector("[data-testid=business-loading]")).not.toBeNull();
    await view.rerender(<Settle pending={false} layout="rows">Listo</Settle>);
    expect(view.host.textContent).toContain("Listo");
    await view.rerender(<Settle pending layout="rows" />);
    expect(view.host.querySelector("[data-testid=business-loading]")).toBeNull();
    expect(view.host.textContent ?? "").not.toContain("Cargando");
    await view.close();
  });
});
