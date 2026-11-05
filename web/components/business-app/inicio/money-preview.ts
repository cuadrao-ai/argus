// DRAFT (design lane): local-preview states for Home's Por cobrar and Por pagar cards, `?money=current|empty|long`.
// Each reshapes the real open-items response and recomputes its counts and totals from the rows, so the cards
// render exactly what the server would send for that data. Outside the local preview the response passes through.
import type { MonthCloseDocument, OpenItems, OpenItemsList, OpenItemsTotal } from "@/lib/business-month-close";

type MoneyPreview = "current" | "empty" | "long";

function moneyPreview(): MoneyPreview | null {
  // Sample states are a local design tool: development with mock sign-in only, never a real Business.
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true" || typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("money");
  return value === "current" || value === "empty" || value === "long" ? value : null;
}

const cents = (value: string) => { const [whole, fraction = ""] = value.split("."); return BigInt(whole + fraction.padEnd(2, "0").slice(0, 2)); };
const HUNDRED = BigInt(100);
const decimal = (value: bigint) => `${value / HUNDRED}.${(value % HUNDRED).toString().padStart(2, "0")}`;

function totalsOf(items: readonly MonthCloseDocument[]): OpenItemsTotal[] {
  const sums = new Map<string, bigint>();
  for (const item of items) if (item.currency && item.amount) sums.set(item.currency, (sums.get(item.currency) ?? BigInt(0)) + cents(item.amount));
  return [...sums].map(([currency, total]) => ({ currency, total: decimal(total) }));
}

function listOf(items: MonthCloseDocument[], today: string | null): OpenItemsList {
  const overdue = items.filter((item) => today !== null && item.due_on !== null && item.due_on < today);
  return { count: items.length, totals: totalsOf(items), overdue: { count: overdue.length, totals: totalsOf(overdue) }, items };
}

/** Ten-million-scale amounts, a long counterparty and a second currency, to prove nothing overflows. */
function long(items: readonly MonthCloseDocument[]): MonthCloseDocument[] {
  const scaled = items.map((item, index) => ({
    ...item,
    amount: item.amount ? decimal(cents(item.amount) * BigInt(1000)) : item.amount,
    counterparty: index === 0 ? "Distribuidora Internacional de Materiales y Ferretería del Cibao" : item.counterparty,
  }));
  const first = scaled[0];
  return first ? [...scaled, { ...first, id: `${first.id}-usd`, currency: "USD", amount: "184250.75", counterparty: "Proveedor en dólares" }] : scaled;
}

export function previewOpenItems(open: OpenItems): OpenItems {
  const mode = moneyPreview();
  if (mode === null) return open;
  const shape = (list: OpenItemsList) => {
    const items = mode === "empty" ? [] : mode === "long" ? long(list.items) : list.items.filter((item) => item.due_on === null || open.today === null || item.due_on >= open.today);
    return listOf(items, open.today);
  };
  return { ...open, cuentas_por_cobrar: shape(open.cuentas_por_cobrar), cuentas_por_pagar: shape(open.cuentas_por_pagar) };
}
