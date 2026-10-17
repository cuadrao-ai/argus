import { sampleInvoiceStory } from "./sample-data";

export type SamplePriority =
  | { kind: "collection"; id: string; story: typeof sampleInvoiceStory }
  | { kind: "payable"; id: string; supplier: string; amount: number; due: "tomorrow" }
  | { kind: "document"; id: string; expense: { es: string; en: string }; amount: number };

export const sampleExpenseStory = {
  expense: { kind: "document", id: "expense-316", expense: { es: "Transporte local", en: "Local transport" }, amount: 2800 } satisfies SamplePriority,
  receipt: { id: "R-0316", filename: "recibo-transporte.pdf", supplier: "Transporte del Norte", date: { es: "6 de octubre", en: "October 6" } },
} as const;

export const samplePriorities: readonly SamplePriority[] = [
  { kind: "collection", id: "collection-1024", story: sampleInvoiceStory },
  { kind: "payable", id: "supplier-208", supplier: "Suministros del Cibao", amount: 12500, due: "tomorrow" },
  sampleExpenseStory.expense,
];

export function priorityAmount(priority: SamplePriority): number {
  return priority.kind === "collection"
    ? priority.story.invoice.amount - priority.story.payment
    : priority.amount;
}

export function priorityName(priority: SamplePriority, locale: "es" | "en"): string {
  switch (priority.kind) {
    case "collection": return priority.story.customerName;
    case "payable": return priority.supplier;
    case "document": return priority.expense[locale];
  }
}

export const priorityCopy = {
  es: {
    title: "Qué necesita atención.",
    intro: "Un cobro pendiente, un pago próximo y un gasto por completar. Cada uno con su contexto.",
    preview: "Vista inicial · datos ficticios · experiencia en desarrollo",
    count: "asuntos por revisar",
    next: "Próximo paso sugerido",
    detail: "Detalle del asunto seleccionado",
    collection: { label: "Por cobrar", status: "Saldo pendiente", payment: "Abono recibido", reason: "La factura tiene un abono registrado. Falta acordar cuándo llegará el resto.", next: "Confirmar el próximo abono con el cliente.", action: "Ver factura y abono" },
    payable: { label: "Por pagar", status: "Vence mañana", reason: "El pago a este proveedor está próximo. Conviene revisar el vencimiento antes de programarlo.", next: "Confirmar la fecha de pago." },
    document: { label: "Por completar", status: "Falta comprobante", reason: "El gasto está registrado, pero aún falta el documento que lo respalda.", next: "Reunir el comprobante." },
  },
  en: {
    title: "What needs attention.",
    intro: "An outstanding balance, an upcoming payment and an expense missing its receipt. Each with its context.",
    preview: "Starting view · fictional data · experience in development",
    count: "items to review",
    next: "Suggested next step",
    detail: "Selected item details",
    collection: { label: "To collect", status: "Outstanding balance", payment: "Payment received", reason: "A partial payment is recorded against this invoice. The next step is agreeing when the rest will arrive.", next: "Confirm the next payment with the customer.", action: "View invoice and payment" },
    payable: { label: "To pay", status: "Due tomorrow", reason: "This supplier payment is coming up. Review the due date before scheduling it.", next: "Confirm the payment date." },
    document: { label: "To complete", status: "Receipt needed", reason: "The expense is recorded, but its supporting document is still missing.", next: "Gather the receipt." },
  },
} as const;
