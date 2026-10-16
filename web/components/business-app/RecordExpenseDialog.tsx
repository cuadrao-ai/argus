"use client";

import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import MoneyInput, { type MoneyInputChange } from "@/components/money/MoneyInput";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { EXPENSE_ACCOUNT_TYPES, type BusinessAccount, type ExpenseAccountType } from "@/lib/business-api";
import { moneyProblemFromServer } from "@/lib/money-entry";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "./BusinessWorkspace";
import { RECEIPT_CATEGORY_IDS } from "./business-format";
import { primaryButtonClass, secondaryButtonClass, useCategoryLabel, useOwnerView } from "./business-ui";

const inputClass =
  "mt-1.5 block min-h-11 w-full rounded-[12px] border border-black/10 bg-white px-3 text-[16px] text-black outline-none focus-visible:border-black/30 focus-visible:ring-[0.125rem] focus-visible:ring-black/10 dark:border-white/10 dark:bg-[#141517] dark:text-white";

/** The currencies a new account is offered in; the API accepts more, this list is the product's. */
const ACCOUNT_CURRENCIES = ["DOP", "USD"] as const;

function today(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export default function RecordExpenseDialog({
  isOpen,
  onClose,
  onRecorded,
}: {
  isOpen: boolean;
  onClose: () => void;
  onRecorded: () => void;
}) {
  if (!isOpen) return null;
  return <RecordExpenseSurface onClose={onClose} onRecorded={onRecorded} />;
}

function RecordExpenseSurface({ onClose, onRecorded }: { onClose: () => void; onRecorded: () => void }) {
  const { t } = useTranslation();
  const categoryLabel = useCategoryLabel();
  const { source, records } = useBusiness();
  const owner = useOwnerView();
  // The account made here is the server's answer; it stands until the workspace reload lists it.
  const [added, setAdded] = useState<BusinessAccount | null>(null);
  const listed = records.workspace?.accounts ?? [];
  const accounts = added && !listed.some((item) => item.id === added.id) ? [...listed, added] : listed;
  const settingUp = owner && accounts.length === 0;
  const noteId = useId();
  const [merchant, setMerchant] = useState("");
  const [amount, setAmount] = useState<MoneyInputChange>({ value: null, invalid: false });
  const [amountError, setAmountError] = useState<string | null>(null);
  const [occurredOn, setOccurredOn] = useState(today);
  const [categoryId, setCategoryId] = useState("");
  const [chosenAccountId, setAccountId] = useState("");
  const accountId = chosenAccountId || accounts[0]?.id || "";
  const [state, setState] = useState<"idle" | "saving" | "failed">("idle");
  const [problem, setProblem] = useState<string | null>(null);
  // One key per submitted expense, so a retry replays it and an edit is new.
  const key = useRef<{ payload: string; key: string } | null>(null);
  const account = accounts.find((item) => item.id === accountId);
  const valid = Boolean(accountId && amount.value && !amount.invalid && occurredOn);
  const saving = state === "saving";
  // Closing waits for the save, so its result always lands somewhere.
  const close = () => {
    if (!saving) onClose();
  };

  const save = async () => {
    if (!valid || !amount.value) return;
    setState("saving");
    setProblem(null);
    const input = {
      account_id: accountId,
      amount: amount.value,
      occurred_on: occurredOn,
      merchant: merchant.trim() || null,
      category_id: categoryId || null,
    };
    const payload = JSON.stringify(input);
    if (key.current?.payload !== payload) key.current = { payload, key: randomId() };
    try {
      await source.recordExpense(input, key.current.key);
      onRecorded();
    } catch (error) {
      const { status, message, code } = error as { status?: number; message?: string; code?: string };
      if (account && moneyProblemFromServer(code, account.currency)) {
        setAmountError(code ?? null);
        setState("idle");
        return;
      }
      setProblem(status === 400 || status === 422 ? message || null : null);
      setState("failed");
    }
  };

  return (
    <AdaptivePanel
      title={t("business.actions.record_expense", "Record expense")}
      closeLabel={t("common.close", "Close")}
      onClose={close}
      width="md"
      footer={
        <div className="flex justify-end gap-2 px-4 pb-4">
          <button type="button" className={secondaryButtonClass} disabled={saving} onClick={close}>
            {t("common.cancel", "Cancel")}
          </button>
          <button type="button" className={primaryButtonClass} disabled={!valid || saving} onClick={() => void save()}>
            {saving ? t("business.review.confirming", "Saving…") : t("business.record.save", "Save expense")}
          </button>
        </div>
      }
    >
      <div className="space-y-4 px-4 pb-2">
        {accounts.length === 0 ? (
          <p id={noteId} className="text-[14px] text-black/65 dark:text-white/65">
            {t("business.record.no_accounts", "Add a business account first so we know where this expense was paid from.")}
          </p>
        ) : null}
        {settingUp ? (
          <AddPaidFromAccount
            labelledBy={noteId}
            onAdded={(account) => {
              setAdded(account);
              setAccountId(account.id);
            }}
          />
        ) : null}
        <label className="block text-[13px] font-medium text-black/60 dark:text-white/60">
          {t("business.review.merchant", "Merchant")}
          <input className={inputClass} value={merchant} onChange={(event) => setMerchant(event.target.value)} autoComplete="off" />
        </label>
        <div className="grid grid-cols-2 items-start gap-3">
          <label className="block text-[13px] font-medium text-black/60 dark:text-white/60">
            {account
              ? t("business.record.amount_in", "Total in {{currency}}", { currency: account.currency })
              : t("business.review.amount", "Total")}
            <MoneyInput
              label={t("business.review.amount", "Total")}
              currency={account?.currency ?? ""}
              value={amount.value}
              onValueChange={(change) => {
                setAmount(change);
                setAmountError(null);
              }}
              serverError={amountError}
              testId="record-expense-amount"
            />
          </label>
          <label className="block text-[13px] font-medium text-black/60 dark:text-white/60">
            {t("business.review.date", "Date")}
            <input type="date" className={inputClass} value={occurredOn} onChange={(event) => setOccurredOn(event.target.value)} />
          </label>
        </div>
        {settingUp ? null : <label className="block text-[13px] font-medium text-black/60 dark:text-white/60">
          {t("business.review.account", "Paid from")}
          <select className={inputClass} value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>{`${item.nickname ?? item.type} · ${item.currency}`}</option>
            ))}
          </select>
        </label>}
        <label className="block text-[13px] font-medium text-black/60 dark:text-white/60">
          {t("business.review.category", "Category")}
          <select className={inputClass} value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
            <option value="">{categoryLabel(null)}</option>
            {RECEIPT_CATEGORY_IDS.map((id) => (
              <option key={id} value={id}>{categoryLabel(id)}</option>
            ))}
          </select>
        </label>
        {state === "failed" ? (
          <p role="alert" className="text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">
            {problem ?? t("business.record.failed", "We couldn't save this expense. Try again. It won't be saved twice.")}
          </p>
        ) : null}
      </div>
    </AdaptivePanel>
  );
}

/** The owner's first account, set up where the expense is recorded; the dialog chooses it once the server answers. */
function AddPaidFromAccount({ labelledBy, onAdded }: { labelledBy: string; onAdded: (account: BusinessAccount) => void }) {
  const { t } = useTranslation();
  const { source, reload } = useBusiness();
  const [nickname, setNickname] = useState("");
  const [type, setType] = useState<ExpenseAccountType>("cash");
  const [currency, setCurrency] = useState<(typeof ACCOUNT_CURRENCIES)[number]>("DOP");
  const [state, setState] = useState<"idle" | "adding" | "failed">("idle");
  // One key per account request, so a retry after a lost answer replays it instead of adding a second account.
  const key = useRef<{ payload: string; key: string } | null>(null);
  const adding = state === "adding";
  const input = { nickname: nickname.trim(), type, currency };
  const label = "block text-[13px] font-medium text-black/60 dark:text-white/60";

  const add = async () => {
    if (!input.nickname || adding) return;
    setState("adding");
    const payload = JSON.stringify(input);
    if (key.current?.payload !== payload) key.current = { payload, key: randomId() };
    try {
      const account = await source.createAccount(input, key.current.key);
      reload();
      onAdded(account);
    } catch {
      setState("failed");
    }
  };

  return (
    <div role="group" aria-labelledby={labelledBy} className="space-y-3 rounded-[12px] border border-black/10 p-3 dark:border-white/10">
      <label className={label}>
        {t("business.record.account_name", "Name")}
        <input className={inputClass} value={nickname} maxLength={60} onChange={(event) => setNickname(event.target.value)} disabled={adding} autoComplete="off" />
      </label>
      <div className="grid grid-cols-2 items-start gap-3">
        <label className={label}>
          {t("business.record.account_type", "Account type")}
          <select className={inputClass} value={type} onChange={(event) => setType(event.target.value as ExpenseAccountType)} disabled={adding}>
            {EXPENSE_ACCOUNT_TYPES.map((item) => (
              <option key={item} value={item}>{t(`business.record.account_types.${item}`)}</option>
            ))}
          </select>
        </label>
        <label className={label}>
          {t("business.review.currency", "Currency")}
          <select className={inputClass} value={currency} onChange={(event) => setCurrency(event.target.value as (typeof ACCOUNT_CURRENCIES)[number])} disabled={adding}>
            {ACCOUNT_CURRENCIES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
      </div>
      {state === "failed" ? (
        <p role="alert" className="text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">
          {t("common.error_occurred", "An error occurred")}
        </p>
      ) : null}
      <button type="button" className={secondaryButtonClass} disabled={!input.nickname || adding} aria-busy={adding} onClick={() => void add()}>
        {t("business.record.add_account", "Add account")}
      </button>
    </div>
  );
}
