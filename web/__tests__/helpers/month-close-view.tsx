import type { MonthCloseClient } from "../../lib/business-month-close";

/** Inicio's month-close view in Spanish on a fresh root, the way the Business app mounts it. */
export async function renderMonthCloseView(client: MonthCloseClient, now: Date, businessCurrency: string | null = null) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../../public/locales/es-419/common.json")).default;
  const { BusinessMonthCloseView } = await import("../../components/business-app/BusinessMonthClosePanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessMonthCloseView client={client} now={now} businessCurrency={businessCurrency} />
      </I18nextProvider>,
    );
  });
  await act(async () => {
    await Promise.resolve();
  });
  return { act, host, root };
}
