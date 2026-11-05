import { formatRnc } from "@/lib/rnc-status";
import type { InvoiceCustomer } from "./invoice-preview-model";

export const CUSTOMER_FIELD_LIMITS = { name: 120, email: 254, taxId: 120, address: 240 } as const;

function domesticTaxId(value: string): boolean {
  const digits = value.replace(/[ -]/g, "");
  return /^(?:[0-9]{9}|[0-9]{11})$/.test(digits) && !/^0+$/.test(digits);
}

export function formatCustomerTaxId(value: string): string {
  return domesticTaxId(value.trim()) ? formatRnc(value) : value;
}

export function customerErrors(customer: InvoiceCustomer, requireDomesticTaxId = false, limits: { [K in keyof typeof CUSTOMER_FIELD_LIMITS]: number | undefined } = CUSTOMER_FIELD_LIMITS): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!customer.name.trim()) errors.name = "required";
  else if (customer.name.length > (limits.name ?? Infinity)) errors.name = "name_length";
  if (customer.email && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(customer.email) || customer.email.length > (limits.email ?? Infinity))) errors.email = "email";
  const taxId = customer.taxId.trim();
  if (requireDomesticTaxId || taxId && /^[0-9 -]+$/.test(taxId)) {
    if (!domesticTaxId(taxId)) errors.taxId = "tax_id";
  } else if (taxId.length > (limits.taxId ?? Infinity)) errors.taxId = "tax_id_length";
  if (customer.address.length > (limits.address ?? Infinity)) errors.address = "address_length";
  return errors;
}
