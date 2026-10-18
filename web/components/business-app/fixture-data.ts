import type {
  BusinessAccount,
  BusinessExpense,
  BusinessUpdate,
  ReceiptDetail,
  ReceiptReviewFields,
  BusinessAccessGrant,
  BusinessAccessInvite,
} from "@/lib/business-api";
import { createDossierFixtures, dossierFixtureIds } from "./dossier-fixtures";
import { normalizeSearchText } from "@/lib/search-text";
import type { BusinessDataSource } from "./business-data";

/**
 * Synthetic records for the local design preview only. Every merchant and
 * amount is invented; the preview labels itself as sample data.
 */

const ACCOUNTS: BusinessAccount[] = [
  { id: "acct-ops", nickname: "Operating account", type: "checking", currency: "DOP" },
  { id: "acct-card", nickname: "Business card", type: "credit_card", currency: "USD" },
];

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

/** The local calendar day, matching how the period filter builds its range. */
function dayOnly(iso: string): string {
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function receipt(
  partial: Partial<ReceiptDetail> & Pick<ReceiptDetail, "id" | "status">,
): ReceiptDetail {
  return {
    channel: "web",
    filename: `${partial.id}.jpg`,
    media_type: "image/jpeg",
    size_bytes: 412_000,
    received_at: daysAgo(1),
    error_code: null,
    attention: null,
    preparable: false,
    enterable: partial.status === "review_ready",
    read_pending: partial.status === "queued" || partial.status === "preparing",
    expense_id: null,
    merchant: null,
    occurred_on: null,
    amount: null,
    currency: null,
    category_id: null,
    account_id: null,
    record_context: { space_id: "fixture-space", space_name: "Mi negocio", accounts: ACCOUNTS, capabilities: ["read", "prepare", "approve"] },
    draft_id: null,
    version: 1,
    evidence: null,
    missing_fields: [],
    ...partial,
  };
}

/** What the backend lists for a receipt nobody has read. */
const UNREAD: ReceiptDetail["missing_fields"] = ["account_id", "amount", "currency", "occurred_on"];

function seedReceipts(): ReceiptDetail[] {
  return [
    receipt({
      id: "rcpt-ferreteria",
      fiscal_known: true,
      status: "review_ready",
      channel: "whatsapp",
      personal_editable: true,
      filename: "IMG_2214.jpg",
      received_at: daysAgo(0),
      merchant: "Ferretería La Esquina",
      occurred_on: dayOnly(daysAgo(0)),
      amount: "3450.00",
      currency: "DOP",
      category_id: "other",
      missing_fields: ["account_id"],
      evidence: {
        merchant: "FERRETERIA LA ESQUINA SRL",
        occurred_on: dayOnly(daysAgo(0)),
        total: "3450.00",
        currency: "DOP",
        tax: "526.27",
        tip: null,
        service: null,
        lines: [
          { description: "Pintura blanca 1 gal", amount: "1850.00" },
          { description: "Brochas x3", amount: "1073.73" },
        ],
      },
    }),
    receipt({
      id: "rcpt-papeleria",
      fiscal_known: true,
      status: "review_ready",
      draft_id: dossierFixtureIds.unprepared,
      // The accountant marked it Personal; the owner sees who and can take it back.
      personal: true,
      personal_marked_by: "Marta",
      personal_editable: true,
      enterable: false,
      filename: "papeleria-oct.pdf",
      media_type: "application/pdf",
      received_at: daysAgo(1),
      merchant: "Papelería Central",
      occurred_on: dayOnly(daysAgo(2)),
      amount: "980.50",
      currency: "DOP",
      category_id: "shopping",
      account_id: "acct-ops",
      evidence: {
        merchant: "Papeleria Central",
        occurred_on: dayOnly(daysAgo(2)),
        total: "980.50",
        currency: "DOP",
        tax: "149.57",
        tip: null,
        service: null,
        lines: [],
      },
    }),
    receipt({
      id: "rcpt-blurry",
      status: "needs_attention",
      channel: "whatsapp",
      filename: "IMG_2209.jpg",
      received_at: daysAgo(2),
      error_code: "unreadable_document",
      attention: "unreadable",
      enterable: true,
      version: 0,
      missing_fields: UNREAD,
    }),
    receipt({
      id: "rcpt-unknown",
      status: "needs_attention",
      filename: "IMG_2215.jpg",
      received_at: daysAgo(2),
      error_code: "document_preparation_outcome_unknown",
      attention: "outcome_unknown",
      preparable: true,
      enterable: true,
      version: 0,
      missing_fields: UNREAD,
    }),
    receipt({
      id: "rcpt-ambiguous",
      status: "needs_attention",
      filename: "colmado-oct.jpg",
      received_at: daysAgo(3),
      error_code: "receipt_purchase_ambiguous",
      attention: "several_purchases",
      enterable: true,
      version: 0,
      missing_fields: UNREAD,
      evidence: {
        merchant: "COLMADO DON PEDRO",
        occurred_on: dayOnly(daysAgo(3)),
        total: "706.10",
        currency: "DOP",
        tax: null,
        tip: null,
        service: null,
        lines: [
          { description: "Arroz 5 lb", amount: "325.00" },
          { description: "Aceite 1 L", amount: "410.00" },
        ],
      },
    }),
    receipt({
      id: "rcpt-saved",
      email_delivery_ids: ["email-ferreteria"],
      email_original: true,
      status: "saved",
      filename: "almuerzo-cliente.png",
      media_type: "image/png",
      received_at: daysAgo(3),
      preparable: true,
      enterable: true,
      version: 0,
      missing_fields: UNREAD,
    }),
    receipt({
      id: "rcpt-confirmed",
      fiscal_known: true,
      status: "confirmed",
      filename: "hosting-sep.pdf",
      media_type: "application/pdf",
      received_at: daysAgo(6),
      merchant: "Nube Hosting",
      occurred_on: dayOnly(daysAgo(6)),
      amount: "24.00",
      currency: "USD",
      category_id: "other",
      account_id: "acct-card",
      expense_id: "exp-hosting",
      fiscal_value: "ncf",
      personal_editable: true,
    }),
  ];
}

function seedExpenses(): BusinessExpense[] {
  return [
    {
      id: "exp-hosting",
      fiscal_known: true,
      merchant: "Nube Hosting",
      amount: "24.00",
      currency: "USD",
      category_id: "other",
      account_id: "acct-card",
      occurred_on: dayOnly(daysAgo(6)),
      receipt_id: "rcpt-confirmed",
      draft_id: null,
      fiscal_value: "ncf",
    },
    {
      id: "exp-gas",
      fiscal_known: true,
      merchant: "Estación Ruta 3",
      amount: "2100.00",
      currency: "DOP",
      category_id: "transport",
      account_id: "acct-ops",
      occurred_on: dayOnly(daysAgo(4)),
      receipt_id: null,
      draft_id: null,
    },
    {
      id: "exp-lunch",
      fiscal_known: true,
      merchant: "Comedor Doña Ana",
      amount: "1250.00",
      currency: "DOP",
      category_id: "dining",
      account_id: null,
      funding: "owner_funds",
      occurred_on: dayOnly(daysAgo(8)),
      receipt_id: null,
      draft_id: null,
      personal: true,
      personal_marked_by: "Marta",
    },
  ];
}

function sampleReceiptImage(detail: ReceiptDetail): Blob {
  const lines = [
    detail.evidence?.merchant ?? detail.merchant ?? "RECEIPT",
    detail.occurred_on ?? "",
    ...(detail.evidence?.lines ?? []).map(
      (line) => `${line.description}  ${line.amount ?? ""}`,
    ),
    detail.amount ? `TOTAL ${detail.currency ?? ""} ${detail.amount}` : "",
    "SAMPLE DATA",
  ].filter(Boolean);
  const text = lines
    .map(
      (line, index) =>
        `<text x="24" y="${56 + index * 30}" font-family="monospace" font-size="16" fill="#191c1f">${line
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")}</text>`,
    )
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="520" viewBox="0 0 360 520"><rect width="360" height="520" fill="#fffdf7"/><rect x="8" y="8" width="344" height="504" fill="none" stroke="#d9d4c7" stroke-dasharray="4 4"/>${text}</svg>`;
  return new Blob([svg], { type: "image/svg+xml" });
}

/**
 * Lets a browser test have the next write or search fail with a backend error code, the
 * way the live API answers, so each dialog's error mapping can be seen. The
 * preview only; the live source has no such switch.
 */
function injectedWriteError() {
  const holder = globalThis as { __businessFixtureFailNextWrite?: string };
  const code = holder.__businessFixtureFailNextWrite;
  if (!code) return null;
  delete holder.__businessFixtureFailNextWrite;
  return Object.assign(new Error(code), { status: 422, code });
}

function fold(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

/** Close to the API's rule, for sample data: every query word inside the record's text. */
function matches(query: string, text: string): boolean {
  const words = normalizeSearchText(fold(query)).split(" ").filter(Boolean);
  const haystack = normalizeSearchText(fold(text));
  return words.length > 0 && words.every((word) => haystack.includes(word));
}

const delay = (ms = 240) => new Promise((resolve) => setTimeout(resolve, ms));

/** `accounts: "none"` starts a Business that has no account yet, as a new one does. */
export type FixtureOptions = Readonly<{ chatAvailable: boolean; accounts?: "none" }>;

/** Sample access: the owner and one accountant with read and prepare. */
const access: { grants: BusinessAccessGrant[]; invites: BusinessAccessInvite[] } = {
  grants: [
    { id: "grant-owner", email: null, display_name: "Lucía", capabilities: ["read", "prepare", "approve"], created_at: "2026-10-01T12:00:00Z", owner: true },
    { id: "grant-contadora", email: "contadora@example.test", display_name: "Marta", capabilities: ["read", "prepare"], created_at: "2026-10-05T15:30:00Z", owner: false },
  ],
  invites: [],
};

// The sample's memory of dismissed access lines; the live app keeps it server side.
const seenGrants = new Set<string>();

export function createFixtureBusinessDataSource(
  { chatAvailable, accounts: start }: FixtureOptions = { chatAvailable: true },
): BusinessDataSource {
  const accounts: BusinessAccount[] = start === "none" ? [] : [...ACCOUNTS];
  const createdAccounts = new Map<string, BusinessAccount>();
  let receipts = seedReceipts();
  let expenses = seedExpenses();
  let counter = 0;
  const uploads = new Map<string, ReceiptDetail>();

  const find = (id: string) => {
    const found = receipts.find((item) => item.id === id);
    if (!found) throw Object.assign(new Error("not_found"), { status: 404 });
    return found;
  };
  const replace = (next: ReceiptDetail) => {
    receipts = receipts.map((item) => (item.id === next.id ? next : item));
    return next;
  };
  const required: (keyof ReceiptReviewFields)[] = ["merchant", "occurred_on", "amount", "currency", "account_id"];
  const missing = (fields: ReceiptReviewFields) => required.filter((key) => !fields[key]);
  const { createReceiptDraft, ...dossierSource } = createDossierFixtures(ACCOUNTS);

  return {
    mode: "fixture",
    ...dossierSource,
    approveDraft: async (id, version, key) => {
      const dossier = await dossierSource.approveDraft(id, version);
      const receipt = receipts.find((item) => item.draft_id === id);
      if (receipt && dossier.approval_result?.status === "recorded") {
        const facts = dossier.facts;
        if (facts.amount.state === "known" && facts.currency.state === "known" && facts.occurred_on.state === "known" && facts.funding.state === "known" && facts.funding.value.kind === "business_account") {
          expenses = [{ id: dossier.approval_result.activity_id, fiscal_known: true, merchant: facts.counterparty.value, amount: facts.amount.value, currency: facts.currency.value, category_id: facts.category_id.value, account_id: facts.funding.value.account_id, occurred_on: facts.occurred_on.value, receipt_id: receipt.id, draft_id: id }, ...expenses];
          replace({ ...receipt, status: "confirmed", expense_id: dossier.approval_result.activity_id });
        }
      }
      void key;
      return dossier;
    },
    ensureSpace: async () => {
      await delay();
      return { id: "fixture-space", name: "Mi negocio" };
    },
    spaces: async () => {
      await delay();
      return [
        { space_id: "fixture-space", name: "Mi negocio", grant_id: "fixture-grant-own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true },
        { space_id: "fixture-client", name: "Colmado Peña", grant_id: "fixture-grant-client", role: "accountant", capabilities: ["read", "prepare"], access_seen: seenGrants.has("fixture-grant-client") },
      ];
    },
    markAccessSeen: async (grantId: string) => {
      await delay();
      seenGrants.add(grantId);
    },
    workspace: async () => {
      await delay();
      return {
        accounts: [...accounts],
        currencies: [...new Set(accounts.map((item) => item.currency))].sort(),
        assistant_available: true,
        chat_available: chatAvailable,
        receipt_limits: {
          max_bytes: 10 * 1024 * 1024,
          media_types: ["application/pdf", "image/jpeg", "image/png"],
        },
      };
    },
    overview: async (from, end) => {
      await delay();
      const today = new Date().toISOString().slice(0, 10);
      const to = end ?? today;
      const inPeriod = expenses.filter(
        (item) => item.occurred_on >= from && item.occurred_on <= to,
      );
      const byCurrency = new Map<string, { amount: number; count: number }>();
      for (const item of inPeriod) {
        const current = byCurrency.get(item.currency) ?? { amount: 0, count: 0 };
        byCurrency.set(item.currency, {
          amount: current.amount + Number(item.amount),
          count: current.count + 1,
        });
      }
      const sum = (items: typeof inPeriod) => {
        const by = new Map<string, { amount: number; count: number }>();
        for (const item of items) {
          const current = by.get(item.currency) ?? { amount: 0, count: 0 };
          by.set(item.currency, { amount: current.amount + Number(item.amount), count: current.count + 1 });
        }
        return [...by.entries()].map(([currency, total]) => ({ currency, amount: total.amount.toFixed(2), count: total.count }));
      };
      const real = inPeriod.filter((item) => !item.personal);
      return {
        from,
        to,
        today,
        totals: sum(real),
        fiscal_totals: sum(real.filter((item) => item.fiscal_value)),
        without_fiscal_totals: sum(real.filter((item) => !item.fiscal_value)),
        outside_period_count: expenses.length - inPeriod.length,
        outside_period_latest_on: expenses.filter((item) => !inPeriod.includes(item)).map((item) => item.occurred_on).sort().at(-1) ?? null,
        last_received_at: receipts[0]?.received_at ?? null,
        last_confirmed_at: daysAgo(6),
      };
    },
    receipts: async (view) => {
      await delay();
      return view === "all"
        ? receipts
        : receipts.filter((item) => item.status !== "confirmed" && item.status !== "dismissed");
    },
    // The sample's stand-in for the server's one count projection: every row
    // the Bandeja lists (never the email itself) plus notes no receipt carries.
    receiptPage: async (view) => {
      await delay();
      const items = view === "all" ? receipts : receipts.filter((item) => item.status !== "confirmed" && item.status !== "dismissed");
      const pending = receipts.filter((item) => !item.email_original && item.status !== "confirmed" && item.status !== "dismissed");
      const notes = new Set((await dossierSource.captures("", 50, "inbox")).map((note) => note.draft_id)).size;
      const reading = receipts.filter((item) => item.read_pending).length;
      const unread = receipts.filter((item) => item.activity?.unread).length;
      return {
        items,
        activity: {
          reading_count: reading,
          unread_count: unread,
          presentation: reading ? "working" : unread ? "unread" : "none",
          pending_review_count: pending.length + notes,
          needs_attention_count: pending.filter((item) => item.status === "needs_attention").length,
        },
      };
    },
    receipt: async (id) => {
      await delay();
      return find(id);
    },
    markPersonal: async (id, version, personal) => {
      await delay();
      // The preview acts as the owner: the owner's own mark names nobody else.
      for (const item of receipts) if (item.id === id || item.draft_id === id) replace({ ...item, personal, personal_marked_by: null });
      for (const item of expenses) if (item.receipt_id === id || item.draft_id === id) Object.assign(item, { personal, personal_marked_by: null });
      void version;
      // The sample receipt behind an unprepared draft has no record to answer with; a ready one stands in.
      const record = await dossierSource.dossier(id).catch(() => dossierSource.dossier(dossierFixtureIds.ready));
      return { ...record, personal, personal_marked_by: null };
    },
    decideFiscalInclusion: async (id, version, include) => {
      await delay();
      for (const item of receipts) if (item.id === id || item.draft_id === id) replace({ ...item, include_606: include });
      for (const item of expenses) if (item.receipt_id === id || item.draft_id === id) item.include_606 = include;
      void version;
      return dossierSource.dossier(id);
    },
    receiptSource: async (id) => {
      await delay(120);
      return sampleReceiptImage(find(id));
    },
    updates: async () => {
      await delay();
      const items: BusinessUpdate[] = receipts
        .filter((item) => ["review_ready", "needs_attention", "confirmed"].includes(item.status))
        .map((item) => ({
          id: `upd-${item.id}`,
          kind:
            item.status === "confirmed"
              ? "expense_confirmed"
              : item.status === "needs_attention"
                ? "receipt_needs_attention"
                : "receipt_ready",
          occurred_at: item.received_at,
          receipt_id: item.id,
          expense_id: item.expense_id,
          error_code: item.error_code,
          attention: item.attention,
          label: item.merchant ?? item.filename,
        }));
      return items;
    },
    expense: async (id) => {
      await delay();
      const found = expenses.find((item) => item.id === id);
      if (!found) throw Object.assign(new Error("expense_not_found"), { status: 404, code: "expense_not_found" });
      return { ...found, recorded_at: `${found.occurred_on}T15:00:00Z`, revision: 1 };
    },
    expenses: async (from, end) => {
      await delay();
      const to = end ?? new Date().toISOString().slice(0, 10);
      return expenses
        .filter((item) => item.occurred_on >= from && item.occurred_on <= to)
        .sort((a, b) => b.occurred_on.localeCompare(a.occurred_on));
    },
    uploadReceipt: async (file, consentToPrepare, key) => {
      await delay(500);
      const earlier = uploads.get(key);
      if (earlier) return earlier;
      counter += 1;
      const created = receipt({
        id: `rcpt-new-${counter}`,
        status: consentToPrepare ? "queued" : "saved",
        filename: file.name,
        media_type: file.type,
        size_bytes: file.size,
        received_at: new Date().toISOString(),
        preparable: !consentToPrepare,
        enterable: !consentToPrepare,
        version: 0,
        missing_fields: UNREAD,
      });
      receipts = [created, ...receipts];
      uploads.set(key, created);
      return created;
    },
    rebindReceipt: async (id) => {
      await delay();
      return find(id);
    },
    prepareReceipt: async (id) => {
      await delay();
      const current = find(id);
      if (!current.preparable) {
        throw Object.assign(new Error("document_busy"), { status: 409, code: "document_busy" });
      }
      return replace({ ...current, status: "queued", error_code: null, attention: null, preparable: false, enterable: false, read_pending: true });
    },
    saveReview: async (id, version, fields) => {
      await delay();
      const current = find(id);
      if (current.version !== version) {
        throw Object.assign(new Error("stale_version"), { status: 409, code: "stale_version" });
      }
      const merged = { ...current, ...fields };
      const injected = injectedWriteError();
      if (injected) throw injected;
      const entered = current.enterable
        ? { status: "review_ready" as const, fiscal_known: true, error_code: null, attention: null, preparable: false, enterable: false }
        : {};
      const reviewed: ReceiptDetail = {
        ...merged,
        ...entered,
        version: current.version + 1,
        missing_fields: missing(merged),
      };
      return replace({ ...reviewed, draft_id: current.draft_id === dossierFixtureIds.unprepared ? current.draft_id : createReceiptDraft(reviewed) });
    },
    confirmReceipt: async (id, version) => {
      await delay(400);
      const current = find(id);
      if (current.expense_id) return current;
      if (current.version !== version) {
        throw Object.assign(new Error("stale_version"), { status: 409, code: "stale_version" });
      }
      if (current.missing_fields.length > 0) {
        throw Object.assign(new Error("missing_fields"), { status: 422, code: "missing_fields" });
      }
      const account = accounts.find((item) => item.id === current.account_id);
      if (account && account.currency !== current.currency) {
        throw Object.assign(new Error("currency_mismatch"), { status: 422, code: "currency_mismatch" });
      }
      const expenseId = `exp-${id}`;
      expenses = [
        {
          id: expenseId,
          merchant: current.merchant,
          amount: current.amount ?? "0",
          currency: current.currency ?? "DOP",
          category_id: current.category_id,
          account_id: current.account_id ?? "acct-ops",
          occurred_on: current.occurred_on ?? dayOnly(new Date().toISOString()),
          receipt_id: id,
        },
        ...expenses,
      ];
      return replace({ ...current, status: "confirmed", expense_id: expenseId });
    },
    search: async (query) => {
      await delay();
      const injected = injectedWriteError();
      if (injected) throw injected;
      const found = expenses
        .filter((item) => matches(query, [item.merchant, item.category_id].join(" ")))
        .sort((a, b) => b.occurred_on.localeCompare(a.occurred_on));
      const listed = new Set(found.map((item) => item.id));
      return {
        expenses: found.slice(0, 5),
        receipts: receipts
          .filter((item) => !listed.has(item.expense_id ?? ""))
          .filter((item) => matches(query, [item.merchant, item.filename, item.amount].join(" ")))
          .slice(0, 5),
        accounts: accounts.filter((item) =>
          matches(query, [item.nickname, item.type, item.currency].join(" ")),
        ).slice(0, 5),
      };
    },
    recordExpense: async (input) => {
      await delay();
      const account = accounts.find((item) => item.id === input.account_id) ?? accounts[0];
      const injected = injectedWriteError();
      if (injected) throw injected;
      counter += 1;
      const created: BusinessExpense = {
        id: `exp-manual-${counter}`,
        merchant: input.merchant,
        amount: input.amount,
        currency: account.currency,
        category_id: input.category_id,
        account_id: account.id,
        occurred_on: input.occurred_on,
        receipt_id: null,
        draft_id: null,
      };
      expenses = [created, ...expenses];
      return created;
    },
    createAccount: async (input, key) => {
      await delay();
      const replayed = createdAccounts.get(key);
      if (replayed) return replayed;
      const injected = injectedWriteError();
      if (injected) throw injected;
      const created = { id: `acct-${createdAccounts.size + 1}-${key.slice(0, 8)}`, ...input };
      createdAccounts.set(key, created);
      accounts.push(created);
      return created;
    },
    emailIntake: async () => {
      await delay();
      return { enabled: true, receiving_address: "recibos-7f3a9c21@recibos.cuadrao.example" };
    },
    createEmailAddress: async () => {
      await delay();
      return { enabled: true, receiving_address: "recibos-7f3a9c21@recibos.cuadrao.example" };
    },
    emailDeliveries: async () => {
      await delay();
      return SAMPLE_EMAILS.map((item) => {
        const { text_body, ...delivery } = item;
        void text_body;
        return delivery;
      });
    },
    emailDelivery: async (id) => {
      await delay();
      const found = SAMPLE_EMAILS.find((item) => item.id === id);
      if (!found) throw Object.assign(new Error("not_found"), { status: 404 });
      return found;
    },
    retryEmailDelivery: async (id) => {
      await delay();
      return { id };
    },
    access: async () => {
      await delay();
      return { grants: [...access.grants], invites: [...access.invites] };
    },
    giveAccess: async (email) => {
      await delay();
      const address = email.trim().toLowerCase();
      if (!address.includes("@")) throw Object.assign(new Error("invalid_email"), { status: 422 });
      if (!access.invites.some((item) => item.email === address) && !access.grants.some((item) => item.email === address)) {
        const now = new Date();
        access.invites.push({ id: `inv-${access.invites.length + 1}`, email: address, created_at: now.toISOString(), expires_at: new Date(now.getTime() + 14 * 86_400_000).toISOString() });
      }
      return { grants: [...access.grants], invites: [...access.invites] };
    },
    revokeAccessGrant: async (id) => {
      await delay();
      const found = access.grants.find((item) => item.id === id);
      if (!found) throw Object.assign(new Error("not_found"), { status: 404 });
      if (found.owner) throw Object.assign(new Error("owner_grant_required"), { status: 409 });
      access.grants = access.grants.filter((item) => item.id !== id);
    },
    revokeAccessInvite: async (id) => {
      await delay();
      access.invites = access.invites.filter((item) => item.id !== id);
    },
  };
}

/** One email whose attachment is the ferretería receipt, and one that could not be read. */
const SAMPLE_EMAILS = [
  {
    id: "email-ferreteria",
    state: "captured" as const,
    received_at: new Date(Date.now() - 50 * 60_000).toISOString(),
    updated_at: new Date(Date.now() - 49 * 60_000).toISOString(),
    original_document_id: "rcpt-saved",
    retryable: false,
    subject: "Factura 0041 Ferretería La Esquina",
    sender: "ventas@ferreterialaesquina.example",
    sent_at: null,
    error_code: null,
    text_body: "Buenas tardes, adjunto la factura de hoy. Gracias por su compra.",
    parts: [
      { id: "1.2", filename: "IMG_2214.jpg", media_type: "image/jpeg", state: "captured" as const, document_id: "rcpt-ferreteria", error_code: null, repeat_of_delivery_id: null },
    ],
  },
  {
    id: "email-boletin",
    state: "rejected" as const,
    received_at: new Date(Date.now() - 26 * 3_600_000).toISOString(),
    updated_at: new Date(Date.now() - 26 * 3_600_000).toISOString(),
    original_document_id: null,
    retryable: false,
    subject: "Boletín semanal",
    sender: "noticias@proveedor.example",
    sent_at: null,
    error_code: "email_parts_rejected",
    text_body: null,
    parts: [
      { id: "1.2", filename: "boletin.zip", media_type: "application/zip", state: "rejected" as const, document_id: null, error_code: "unsupported_media_type" },
    ],
  },
];
