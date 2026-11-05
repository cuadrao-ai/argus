import { expect, test } from "bun:test";
import { invoiceForEditor, draftFromEditor } from "@/components/business-app/invoicing/invoice-editor-adapter";
import { incompleteInvoice, invoiceId } from "./fixtures/business-invoice-fixture";

test("save/reload preserves draft decimal text, complete inputs and unknown fiscal choices", () => {
  const data = incompleteInvoice();
  data.customer_input = { name: "Partial name", email: "", tax_id: "123-456789-0", address: "a".repeat(500), phone: "8095550100", notes: "Keep undisplayed customer notes" };
  data.terms = "t".repeat(500); data.instructions = "i".repeat(500); data.notes = "n".repeat(500);
  data.items = [{ id: "stable-item", description: "d".repeat(160), quantity: "1.250", price: "100.010", tax: "18.00", discount: "0.000", classification: null, tax_treatment: null }];
  data.delivery = { to: "draft@example.test", cc: ["copy@example.test"], message: "Keep full delivery draft" };
  const editor = invoiceForEditor(data, invoiceId);
  expect(draftFromEditor(editor, data, [])).toEqual(data);
  expect(editor.payments).toEqual([]); expect(editor.delivery).toBe("not_sent");
});
