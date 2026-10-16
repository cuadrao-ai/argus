import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import ConversationRetrievalState, { ConversationRetrievalAnnouncement, InitialConversationRetrievalState } from "../components/chat/ConversationRetrievalState";
import { LoadingRows } from "../components/business-app/business-ui";
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
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>));
  return { host, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

describe("Business loading presentation", () => {
  test("a completed fast load never displays or announces a loading indicator", async () => {
    const view = await mount(<InitialConversationRetrievalState business />);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 100)); });
    expect(view.host.textContent).toBe("");
    expect(view.host.querySelector('[role="status"]')).toBeNull();
    expect(view.host.querySelector("img")).toBeNull();
    await view.close();
    await new Promise((resolve) => setTimeout(resolve, 70));
    expect(document.querySelector('[data-testid="conversation-retrieval-state"]')).toBeNull();
  });

  test("a slow load shows the approved line and one polite Spanish announcement", async () => {
    const view = await mount(<InitialConversationRetrievalState business />);
    expect(view.host.textContent).toBe("");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 170)); });
    expect(view.host.querySelector("p")?.textContent).toBe("Cuadrando…");
    const status = view.host.querySelector('[role="status"]');
    expect(status?.textContent).toBe("Cargando Cuadrao");
    expect(status?.getAttribute("aria-live")).toBe("polite");
    expect(view.host.querySelectorAll('[role="status"]').length).toBe(1);
    expect(view.host.textContent).not.toContain("Argus");
    expect(view.host.querySelector("img")?.getAttribute("width")).toBe("28");
    expect(view.host.querySelector("img")?.className).toContain("motion-reduce:animate-none");
    await view.close();
  });

  test("a new loading episode starts with a fresh delay", async () => {
    const first = await mount(<InitialConversationRetrievalState business />);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 170)); });
    expect(first.host.querySelector("p")).not.toBeNull();
    await first.close();
    const next = await mount(<InitialConversationRetrievalState business />);
    expect(next.host.textContent).toBe("");
    await next.close();
  });

  test("cold conversation loading uses the same Spanish presentation", async () => {
    const view = await mount(<><ConversationRetrievalAnnouncement business /><ConversationRetrievalState business state="loading" /></>);
    expect(view.host.querySelector("p")?.textContent).toBe("Cuadrando…");
    expect(view.host.querySelector('[role="status"]')?.textContent).toBe("Cargando Cuadrao");
    await view.close();
  });

  test("English and personal conversation labels retain their canonical copy", async () => {
    const english = await mount(<><ConversationRetrievalAnnouncement business /><ConversationRetrievalState business state="loading" /></>, "en");
    expect(english.host.querySelector("p")?.textContent).toBe(en.chat.opening_conversation);
    await english.close();
    const personal = await mount(<><ConversationRetrievalAnnouncement /><ConversationRetrievalState state="loading" /></>);
    expect(personal.host.querySelector("p")?.textContent).toBe(es.chat.opening_conversation);
    await personal.close();
  });

  for (const layout of ["rows", "overview", "detail"] as const) {
    test(`${layout} skeleton has one localized status and decorative reduced-motion placeholders`, async () => {
      const view = await mount(<LoadingRows rows={4} layout={layout} />);
      expect(view.host.querySelector('[role="status"]')?.getAttribute("aria-label")).toBe(es.common.loading);
      expect(view.host.querySelector('[aria-hidden="true"]')?.className).toContain("motion-reduce:animate-none");
      expect(view.host.querySelectorAll("button, input").length).toBe(0);
      expect(view.host.querySelector('[data-layout]')?.getAttribute("data-layout")).toBe(layout);
      expect(view.host.textContent).toBe("");
      await view.close();
    });
  }
});
