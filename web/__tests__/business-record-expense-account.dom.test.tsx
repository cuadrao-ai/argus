import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount, ExpenseInput, GrantedSpace } from "@/lib/business-api";

// "Registrar gasto" in a Business with no account: the owner sets up the
// account the expense was paid from inside the dialog, then saves the expense
// against it. A client's accountant cannot create accounts and sees only the
// existing note. Real provider, real dialog, a fixture source standing in for
// POST /business/accounts with its idempotent replay.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Colmado Lucía", grant_id: "g-own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const CLIENT: GrantedSpace = { space_id: "s-client", name: "Taller Brito", grant_id: "g-client", role: "accountant", capabilities: ["read", "prepare"], access_seen: true };

type Created = { input: { nickname: string; type: string; currency: string }; key: string };

async function mount({ grant = null as string | null, failCreates = 0 } = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(grant);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const accounts: BusinessAccount[] = [];
  const creates: Created[] = [];
  const recorded: ExpenseInput[] = [];
  let failures = failCreates;
  const source = {
    ...fixture,
    spaces: async () => (grant ? [OWN, CLIENT] : [OWN]),
    workspace: async () => ({ ...(await fixture.workspace()), accounts: [...accounts], currencies: [...new Set(accounts.map((item) => item.currency))] }),
    // The server's contract: one account per Idempotency-Key, an exact replay answers the same account.
    createAccount: async (input: Created["input"], key: string) => {
      creates.push({ input, key });
      if (failures > 0) {
        failures -= 1;
        throw Object.assign(new Error("Service Unavailable"), { status: 503 });
      }
      const replayed = accounts.find((item) => item.id === `acct-${key}`);
      if (replayed) return replayed;
      const created: BusinessAccount = { id: `acct-${key}`, ...input };
      accounts.push(created);
      return created;
    },
    recordExpense: async (input: ExpenseInput, key: string) => {
      recorded.push(input);
      return fixture.recordExpense(input, key);
    },
  };
  let business: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    business = useBusiness();
    return null;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessWorkspaceProvider source={source as never}>
          <Probe />
        </BusinessWorkspaceProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      if (done()) return;
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    }
    assert.ok(done(), "the page settled");
  };
  await settle(() => business !== null && business.records.workspace !== null && business.chosen !== null);
  const button = (name: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === name) as HTMLButtonElement | undefined;
  /** The control inside the label whose own text is `name`. */
  const field = <T extends HTMLElement>(name: string) =>
    [...document.body.querySelectorAll("label")].find((label) => label.firstChild?.textContent?.trim() === name)?.querySelector("input, select") as T | undefined;
  const type = async (element: HTMLInputElement | undefined, value: string) => {
    assert.ok(element, "the field is on screen");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(element, value);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const choose = async (element: HTMLSelectElement | undefined, value: string) => {
    assert.ok(element, "the picker is on screen");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(element, value);
      element.dispatchEvent(new Event("change", { bubbles: true }));
    });
  };
  const click = async (element: HTMLElement | undefined) => {
    assert.ok(element, "the control is on screen");
    await act(async () => { element.click(); });
  };
  const open = async () => {
    const record = business!.actions.create.find((action) => action.id === "record_expense");
    await act(async () => { record!.run(); });
    await settle(() => button("Guardar gasto") !== undefined);
  };
  const close = async () => {
    await act(async () => root.unmount());
    host.remove();
  };
  return { settle, button, field, type, choose, click, open, close, accounts, creates, recorded, business: () => business! };
}

const NOTE = "Primero agrega una cuenta del negocio para saber desde dónde se pagó este gasto.";

describe("Registrar gasto in a Business with no account", () => {
  test("the owner adds the account inside the dialog, it is chosen, and the expense is saved against it", async () => {
    const page = await mount();
    await page.open();
    assert.ok(document.body.textContent?.includes(NOTE), "the existing note explains why");
    assert.equal(page.button("Guardar gasto")?.disabled, true, "nothing to save from yet");
    assert.deepEqual([...(page.field<HTMLSelectElement>("Tipo de cuenta")?.options ?? [])].map((option) => [option.value, option.textContent]), [
      ["cash", "Efectivo"],
      ["checking", "Cuenta corriente"],
      ["savings", "Ahorros"],
      ["credit_card", "Tarjeta de crédito"],
    ]);
    assert.deepEqual([...(page.field<HTMLSelectElement>("Moneda")?.options ?? [])].map((option) => option.value), ["DOP", "USD"]);
    assert.equal(page.button("Añadir cuenta")?.disabled, true, "a name is required");

    await page.type(page.field<HTMLInputElement>("Nombre"), "  Caja chica  ");
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "cash");
    await page.choose(page.field<HTMLSelectElement>("Moneda"), "USD");
    await page.click(page.button("Añadir cuenta"));
    await page.settle(() => page.field<HTMLSelectElement>("Pagado desde")?.value === page.accounts[0]?.id);

    assert.deepEqual(page.creates.map((call) => call.input), [{ nickname: "Caja chica", type: "cash", currency: "USD" }]);
    assert.equal(page.button("Añadir cuenta"), undefined, "the form is done once the account exists");
    assert.equal(page.field("Nombre"), undefined);
    assert.equal(page.field<HTMLSelectElement>("Pagado desde")?.selectedOptions[0]?.textContent, "Caja chica · USD");
    await page.settle(() => page.business().records.workspace?.accounts.length === 1);

    await page.type(document.body.querySelector('[data-testid="record-expense-amount"]') as HTMLInputElement, "850");
    assert.equal(page.button("Guardar gasto")?.disabled, false);
    await page.click(page.button("Guardar gasto"));
    await page.settle(() => page.recorded.length === 1);
    assert.equal(page.recorded[0].account_id, page.accounts[0].id);
    assert.equal(page.recorded[0].amount, "850");
    await page.close();
  });

  test("a failed create keeps the form and its answers, and the retry replays the same request", async () => {
    const page = await mount({ failCreates: 1 });
    await page.open();
    await page.type(page.field<HTMLInputElement>("Nombre"), "Cuenta Popular");
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "checking");
    await page.click(page.button("Añadir cuenta"));
    await page.settle(() => document.body.querySelector('[role="alert"]') !== null);

    assert.equal(document.body.querySelector('[role="alert"]')?.textContent, "Ha ocurrido un error");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Cuenta Popular");
    assert.equal(page.field<HTMLSelectElement>("Tipo de cuenta")?.value, "checking");
    assert.equal(page.field<HTMLSelectElement>("Moneda")?.value, "DOP");
    assert.equal(page.button("Guardar gasto")?.disabled, true);

    await page.click(page.button("Añadir cuenta"));
    await page.settle(() => page.field<HTMLSelectElement>("Pagado desde")?.value === page.accounts[0]?.id);
    // The retry carries the first attempt's key, so an attempt the server did save is replayed, not doubled.
    assert.equal(page.creates.length, 2);
    assert.equal(page.creates[1].key, page.creates[0].key);
    assert.equal(page.accounts.length, 1);
    assert.equal(document.body.querySelector('[role="alert"]'), null);
    await page.close();
  });

  test("an accountant in a client's Business sees the note and no way to add an account", async () => {
    const page = await mount({ grant: CLIENT.grant_id });
    assert.equal(page.business().chosen?.role, "accountant");
    await page.open();
    assert.ok(document.body.textContent?.includes(NOTE));
    assert.equal(page.button("Añadir cuenta"), undefined);
    assert.equal(page.field("Nombre"), undefined);
    assert.equal(page.field("Tipo de cuenta"), undefined);
    assert.equal(page.button("Guardar gasto")?.disabled, true);
    assert.equal(page.creates.length, 0);
    await page.close();
  });
});
