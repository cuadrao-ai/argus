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

/** What the server does with the next create: answers it, refuses it, rejects one field, saves it and the answer is lost, or also fails the next workspace read. */
type Outcome = "ok" | "unavailable" | "nickname_invalid" | "answer_lost" | "answer_and_reload_lost";

const unavailable = () => Object.assign(new Error("Service Unavailable"), { status: 503, code: "service_unavailable" });

async function mount({ grant = null as string | null, outcomes = [] as Outcome[] } = {}) {
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
  const pending = [...outcomes];
  /** Every workspace read and account create, in the order the server saw them. */
  const calls: ("workspace" | "create")[] = [];
  const reads = { failing: 0 };
  const source = {
    ...fixture,
    spaces: async () => (grant ? [OWN, CLIENT] : [OWN]),
    workspace: async () => {
      calls.push("workspace");
      if (reads.failing > 0) {
        reads.failing -= 1;
        throw unavailable();
      }
      return { ...(await fixture.workspace()), accounts: [...accounts], currencies: [...new Set(accounts.map((item) => item.currency))] };
    },
    // The server's contract: one account per Idempotency-Key, an exact replay answers the same account.
    createAccount: async (input: Created["input"], key: string) => {
      calls.push("create");
      creates.push({ input, key });
      const outcome = pending.shift() ?? "ok";
      if (outcome === "unavailable") throw unavailable();
      if (outcome === "nickname_invalid") {
        throw Object.assign(new Error("Validation Error"), {
          status: 422,
          code: "validation_error",
          context: { errors: [{ loc: ["body", "nickname"], type: "string_too_long", msg: "String should have at most 200 characters" }] },
        });
      }
      const replayed = accounts.find((item) => item.id === `acct-${key}`);
      if (replayed) return replayed;
      const created: BusinessAccount = { id: `acct-${key}`, ...input };
      accounts.push(created);
      if (outcome === "answer_and_reload_lost") reads.failing += 1;
      if (outcome === "answer_lost" || outcome === "answer_and_reload_lost") throw unavailable();
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
  const alert = () => document.body.querySelector('[role="alert"]');
  /** The message a field points to with aria-describedby, if the field is marked invalid. */
  const fieldError = (element: HTMLElement | undefined) => {
    assert.ok(element, "the field is on screen");
    if (element.getAttribute("aria-invalid") !== "true") return null;
    return document.getElementById(element.getAttribute("aria-describedby") ?? "");
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
  return { settle, button, field, type, choose, click, open, close, alert, fieldError, accounts, creates, recorded, calls, reads, business: () => business! };
}

const NOTE = "Primero agrega una cuenta del negocio para saber desde dónde se pagó este gasto.";
const CREATE_FAILED = "No pudimos crear la cuenta. Revisa el nombre e inténtalo de nuevo.";

describe("Registrar gasto in a Business with no account", () => {
  /** Waits for Pagado desde to replace the form, then checks the server holds one account and it is the one chosen. */
  const chosenSavedAccount = async (page: Awaited<ReturnType<typeof mount>>) => {
    await page.settle(() => page.field("Pagado desde") !== undefined);
    assert.equal(page.accounts.length, 1, "one account on the server");
    await page.settle(() => page.field<HTMLSelectElement>("Pagado desde")?.value === page.accounts[0].id);
  };

  test("the form starts with Cuenta DOP in DOP and no account type, and waits for a type", async () => {
    const page = await mount();
    await page.open();
    assert.ok(document.body.textContent?.includes(NOTE), "the existing note explains why");
    assert.equal(page.button("Guardar gasto")?.disabled, true, "nothing to save from yet");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Cuenta DOP");
    assert.equal(page.field<HTMLSelectElement>("Moneda")?.value, "DOP");
    assert.deepEqual([...(page.field<HTMLSelectElement>("Moneda")?.options ?? [])].map((option) => option.value), ["DOP", "USD"]);
    assert.equal(page.field<HTMLSelectElement>("Tipo de cuenta")?.value, "", "no account type is chosen for the person");
    assert.deepEqual(
      [...(page.field<HTMLSelectElement>("Tipo de cuenta")?.options ?? [])].filter((option) => !option.disabled).map((option) => [option.value, option.textContent]),
      [
        ["cash", "Efectivo"],
        ["checking", "Cuenta corriente"],
        ["savings", "Ahorros"],
        ["credit_card", "Tarjeta de crédito"],
      ],
    );
    assert.equal(page.button("Añadir cuenta")?.disabled, true, "a type is required");

    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "checking");
    assert.equal(page.button("Añadir cuenta")?.disabled, false);
    await page.type(page.field<HTMLInputElement>("Nombre"), "   ");
    assert.equal(page.button("Añadir cuenta")?.disabled, true, "a name is required");
    await page.close();
  });

  test("the suggested name follows the currency until the person types one, and a typed name is never replaced", async () => {
    const page = await mount();
    await page.open();
    await page.choose(page.field<HTMLSelectElement>("Moneda"), "USD");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Cuenta USD");
    await page.choose(page.field<HTMLSelectElement>("Moneda"), "DOP");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Cuenta DOP");

    await page.type(page.field<HTMLInputElement>("Nombre"), "Caja chica");
    await page.choose(page.field<HTMLSelectElement>("Moneda"), "USD");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Caja chica");
    await page.type(page.field<HTMLInputElement>("Nombre"), "");
    await page.choose(page.field<HTMLSelectElement>("Moneda"), "DOP");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "", "a name the person cleared stays cleared");
    await page.close();
  });

  test("the owner adds the account inside the dialog, it is chosen, and the expense is saved against it", async () => {
    const page = await mount();
    await page.open();
    await page.choose(page.field<HTMLSelectElement>("Moneda"), "USD");
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "cash");
    const sent = page.calls.length;
    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);

    assert.deepEqual(page.calls.slice(sent, sent + 2), ["workspace", "create"], "the accounts are read once before the one create");
    assert.deepEqual(page.creates.map((call) => call.input), [{ nickname: "Cuenta USD", type: "cash", currency: "USD" }]);
    assert.equal(page.button("Añadir cuenta"), undefined, "the form is done once the account exists");
    assert.equal(page.field("Nombre"), undefined);
    assert.equal(page.field<HTMLSelectElement>("Pagado desde")?.selectedOptions[0]?.textContent, "Cuenta USD · USD");
    await page.settle(() => page.business().records.workspace?.accounts.length === 1);

    await page.type(document.body.querySelector('[data-testid="record-expense-amount"]') as HTMLInputElement, "850");
    assert.equal(page.button("Guardar gasto")?.disabled, false);
    await page.click(page.button("Guardar gasto"));
    await page.settle(() => page.recorded.length === 1);
    assert.equal(page.recorded[0].account_id, page.accounts[0].id);
    assert.equal(page.recorded[0].amount, "850");
    await page.close();
  });

  test("the native account-type select keeps the complete Spanish label without ellipsis", async () => {
    const page = await mount();
    await page.open();
    const picker = page.field<HTMLSelectElement>("Tipo de cuenta");
    await page.choose(picker, "checking");
    assert.ok(picker);
    assert.equal(picker.value, "checking");
    assert.equal([...picker.options].find((option) => option.selected)?.textContent, "Cuenta corriente");
    assert.notEqual(getComputedStyle(picker).textOverflow, "ellipsis");
    await page.choose(picker, "credit_card");
    assert.equal(picker.value, "credit_card");
    assert.equal([...picker.options].find((option) => option.selected)?.textContent, "Tarjeta de crédito");
    assert.notEqual(getComputedStyle(picker).textOverflow, "ellipsis");
    await page.close();
  });

  test("a failed create says so under the form, keeps the answers, and the retry replays the same request", async () => {
    const page = await mount({ outcomes: ["unavailable"] });
    await page.open();
    await page.type(page.field<HTMLInputElement>("Nombre"), "Cuenta Popular");
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "checking");
    await page.click(page.button("Añadir cuenta"));
    await page.settle(() => page.alert() !== null);

    assert.equal(page.alert()?.textContent, CREATE_FAILED);
    assert.equal(page.fieldError(page.field<HTMLInputElement>("Nombre")), null, "nothing points at one field");
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Cuenta Popular");
    assert.equal(page.field<HTMLSelectElement>("Tipo de cuenta")?.value, "checking");
    assert.equal(page.field<HTMLSelectElement>("Moneda")?.value, "DOP");
    assert.equal(page.button("Guardar gasto")?.disabled, true);

    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);
    // The retry carries the first attempt's key, so an attempt the server did save is replayed, not doubled.
    assert.equal(page.creates.length, 2);
    assert.equal(page.creates[1].key, page.creates[0].key);
    assert.equal(page.accounts.length, 1);
    assert.equal(page.alert(), null);
    await page.close();
  });

  test("a create the server refuses for the name says so under Nombre, not under the form", async () => {
    const page = await mount({ outcomes: ["nickname_invalid"] });
    await page.open();
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "cash");
    await page.click(page.button("Añadir cuenta"));
    const name = () => page.field<HTMLInputElement>("Nombre");
    await page.settle(() => page.fieldError(name()) !== null);

    const message = page.fieldError(name());
    assert.equal(message?.textContent, CREATE_FAILED);
    assert.equal(message?.previousElementSibling?.contains(name()!), true, "the message sits right under the Nombre field");
    assert.equal(page.fieldError(page.field<HTMLSelectElement>("Tipo de cuenta")), null);
    assert.equal(document.body.textContent?.split(CREATE_FAILED).length, 2, "said once, at the field");
    assert.ok(!document.body.textContent?.includes("validation_error"), "no codes");
    await page.close();
  });

  test("a create whose answer was lost finds the saved account, and closing and reopening adds no second one", async () => {
    const page = await mount({ outcomes: ["answer_lost"] });
    await page.open();
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "cash");
    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);
    assert.equal(page.button("Añadir cuenta"), undefined, "the saved account replaces the form");
    assert.equal(page.field<HTMLSelectElement>("Pagado desde")?.selectedOptions[0]?.textContent, "Cuenta DOP · DOP");

    await page.click(page.button("Cancelar"));
    await page.open();
    assert.equal(page.button("Añadir cuenta"), undefined, "reopening offers no second account");
    assert.equal(page.field<HTMLSelectElement>("Pagado desde")?.value, page.accounts[0].id);
    assert.equal(page.creates.length, 1);
    assert.equal(page.accounts.length, 1);
    await page.close();
  });

  /** A create the server saves but whose answer is lost, and the reload after it fails too: the form still shows no account. */
  const lostAnswerAndReload = async () => {
    const page = await mount({ outcomes: ["answer_and_reload_lost"] });
    await page.open();
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "cash");
    await page.click(page.button("Añadir cuenta"));
    await page.settle(() => page.alert() !== null && page.accounts.length === 1 && page.reads.failing === 0);
    assert.equal(page.alert()?.textContent, CREATE_FAILED);
    assert.ok(page.button("Añadir cuenta"), "the form still offers to add one");
    return page;
  };

  test("after a lost answer and a failed reload, an edited retry chooses the saved account instead of adding a second", async () => {
    const page = await lostAnswerAndReload();
    await page.type(page.field<HTMLInputElement>("Nombre"), "Caja chica");
    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);
    assert.equal(page.field<HTMLSelectElement>("Pagado desde")?.selectedOptions[0]?.textContent, "Cuenta DOP · DOP", "the account the server saved");
    assert.equal(page.creates.length, 1);
    assert.equal(page.accounts.length, 1);
    await page.close();
  });

  test("after a lost answer and a failed reload, closing, reopening and retrying adds no second account", async () => {
    const page = await lostAnswerAndReload();
    await page.click(page.button("Cancelar"));
    await page.open();
    await page.choose(page.field<HTMLSelectElement>("Tipo de cuenta"), "cash");
    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);
    assert.equal(page.creates.length, 1);
    assert.equal(page.accounts.length, 1);
    await page.close();
  });

  test("after a lost answer and a failed reload, the same retry replays the first request", async () => {
    const page = await lostAnswerAndReload();
    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);
    assert.equal(page.creates.length, 2);
    assert.equal(page.creates[1].key, page.creates[0].key);
    assert.equal(page.accounts.length, 1);
    await page.close();
  });

  test("when the accounts cannot be read before a new create, the form says so and sends no create", async () => {
    const page = await lostAnswerAndReload();
    await page.type(page.field<HTMLInputElement>("Nombre"), "Caja chica");
    page.reads.failing = 2;
    await page.click(page.button("Añadir cuenta"));
    await page.settle(() => (page.alert() !== null && page.reads.failing === 0) || page.creates.length > 1);
    assert.equal(page.creates.length, 1, "no create was sent");
    assert.equal(page.accounts.length, 1);
    assert.equal(page.alert()?.textContent, CREATE_FAILED);
    assert.equal(page.field<HTMLInputElement>("Nombre")?.value, "Caja chica");

    await page.click(page.button("Añadir cuenta"));
    await chosenSavedAccount(page);
    assert.equal(page.creates.length, 1);
    assert.equal(page.accounts.length, 1);
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

describe("the account type a new account starts with", () => {
  const account = (id: string, type: string): BusinessAccount => ({ id, nickname: null, type, currency: "DOP" });

  test("is the type most of the Business's accounts have, and none on a tie or with no account", async () => {
    const { preferredAccountType } = await import("@/components/business-app/business-data");
    assert.equal(preferredAccountType([account("a", "checking"), account("b", "cash"), account("c", "checking")]), "checking");
    assert.equal(preferredAccountType([account("a", "checking"), account("b", "cash")]), null);
    assert.equal(preferredAccountType([account("a", "property")]), null, "only a type the form offers");
    assert.equal(preferredAccountType([]), null);
  });
});
