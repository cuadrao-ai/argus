import assert from "node:assert/strict";
import { test } from "bun:test";
import { invoicePreviewSeed } from "../components/business-app/invoicing/invoice-preview-model";
import { customerReducer, customerRecentActivity, seedCustomers } from "../components/business-app/invoicing/customer-preview-model";
import { nextCustomerSchedule, nextOccurrence, occurrenceDate, scheduleErrors, scheduleReducer, type InvoiceSchedule } from "../components/business-app/invoicing/schedule-preview-model";
import { invoiceEmptyKind } from "../components/business-app/invoicing/WorkspaceEmptyState";

const invoices = invoicePreviewSeed("seeded", "Correction");
const customers = seedCustomers(invoices);
const schedule = (): InvoiceSchedule => ({ id: "schedule-one", name: "Monthly service", customerId: invoices[0].customer.id, template: { ...structuredClone(invoices[0]), items: invoices[0].items.map(item => ({ ...item, description: "Monthly service" })) }, anchorDate: "2026-01-31", frequency: "monthly", mode: "draft", status: "active" });

test("schedule dates preserve month-end and leap-year anchors and find the next occurrence", () => {
  assert.equal(occurrenceDate("2026-01-31", "monthly", 1), "2026-02-28");
  assert.equal(occurrenceDate("2026-01-31", "monthly", 2), "2026-03-31");
  assert.equal(occurrenceDate("2024-02-29", "yearly", 1), "2025-02-28");
  assert.equal(occurrenceDate("2024-02-29", "yearly", 4), "2028-02-29");
  assert.equal(occurrenceDate("2026-12-28", "weekly", 1), "2027-01-04");
  assert.equal(occurrenceDate("2026-02-30", "monthly", 1), "");
  assert.equal(nextOccurrence(schedule(), "2026-03-01"), "2026-03-31");
  assert.equal(nextOccurrence(schedule(), "2026-03-31"), "2026-03-31");
});

test("schedule save/edit/pause retains identity and templates while automatic mode stays unavailable", () => {
  const source = schedule();
  assert.deepEqual(scheduleErrors(source, customers), {});
  let state = scheduleReducer([], { type: "save", schedule: source });
  state = scheduleReducer(state, { type: "save", schedule: { ...source, name: "Changed" } });
  assert.equal(state.length, 1);
  assert.equal(state[0].name, "Changed");
  state = scheduleReducer(state, { type: "status", id: source.id, status: "paused" });
  assert.equal(nextCustomerSchedule(state, source.customerId), undefined);
  assert.deepEqual(state[0].template, source.template);
  assert.equal(scheduleErrors(source, customers.map(customer => ({ ...customer, status: "archived" }))).customer, "customer");
  assert.equal(scheduleErrors({ ...source, mode: "automatic" } as unknown as InvoiceSchedule, customers).mode, "schedule_mode");
});

test("empty states distinguish first use, empty stage and filtered results", () => {
  assert.equal(invoiceEmptyKind(0, 0, 0), "first");
  assert.equal(invoiceEmptyKind(4, 0, 0), "stage");
  assert.equal(invoiceEmptyKind(4, 2, 0), "filtered");
  assert.equal(invoiceEmptyKind(4, 2, 1), null);
});

test("unknown customer creation dates stay unknown and saved creation dates survive edits", () => {
  const seeded = customers[0];
  const edited = customerReducer(customers, { type: "save", customer: { ...seeded, name: "Updated" } })[0];
  assert.equal(edited.createdAt, undefined);
  assert.equal(customerRecentActivity(seeded, []).latest, undefined);
  const added = customerReducer([], { type: "save", customer: seeded })[0];
  const changed = customerReducer([added], { type: "save", customer: { ...added, name: "Second" } })[0];
  assert.equal(changed.createdAt, added.createdAt);
  assert.ok(changed.createdAt);
});
