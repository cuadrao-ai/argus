import { type InvoicePreview, validDraft, validIsoDate } from "./invoice-preview-model";
import type { BusinessCustomer } from "./customer-preview-model";
import { todayIso } from "../business-format";

export type InvoiceSchedule = {
  id: string;
  name: string;
  customerId: string;
  template: InvoicePreview;
  anchorDate: string;
  frequency: "weekly" | "monthly" | "yearly";
  mode: "draft";
  status: "active" | "paused";
};
export type ScheduleCommand = { type: "save"; schedule: InvoiceSchedule } | { type: "status"; id: string; status: InvoiceSchedule["status"] };

export function occurrenceDate(anchor: string, frequency: InvoiceSchedule["frequency"], index: number): string {
  if (!validIsoDate(anchor) || !Number.isInteger(index) || index < 0) return "";
  const [year, month, day] = anchor.split("-").map(Number);
  if (frequency === "weekly") return new Date(Date.UTC(year, month - 1, day + index * 7)).toISOString().slice(0, 10);
  const target = new Date(Date.UTC(year + (frequency === "yearly" ? index : 0), month - 1 + (frequency === "monthly" ? index : 0), 1));
  const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  target.setUTCDate(Math.min(day, lastDay));
  return target.toISOString().slice(0, 10);
}

export function scheduleErrors(schedule: InvoiceSchedule, customers: BusinessCustomer[]) {
  const errors: Record<string, string> = {};
  if (!schedule.name.trim() || schedule.name.length > 120) errors.name = "required";
  if (!customers.some(customer => customer.id === schedule.customerId && customer.status === "active")) errors.customer = "customer";
  if (!validIsoDate(schedule.anchorDate)) errors.anchorDate = "date";
  if (!validDraft(schedule.template) || schedule.template.issuance !== "draft") errors.template = "schedule_template";
  if (schedule.mode !== "draft") errors.mode = "schedule_mode";
  return errors;
}

export function scheduleReducer(schedules: InvoiceSchedule[], command: ScheduleCommand): InvoiceSchedule[] {
  if (command.type === "status") return schedules.map(schedule => schedule.id === command.id ? { ...schedule, status: command.status } : schedule);
  const saved = { ...command.schedule, name: command.schedule.name.trim() };
  return schedules.some(schedule => schedule.id === saved.id) ? schedules.map(schedule => schedule.id === saved.id ? saved : schedule) : [...schedules, saved];
}

export function nextOccurrence(schedule: InvoiceSchedule, today = todayIso()) {
  if (!validIsoDate(schedule.anchorDate) || !validIsoDate(today)) return "";
  const start = new Date(`${schedule.anchorDate}T12:00:00Z`);
  const now = new Date(`${today}T12:00:00Z`);
  let index = Math.max(0, schedule.frequency === "weekly" ? Math.floor((now.getTime() - start.getTime()) / 604800000) : schedule.frequency === "monthly" ? (now.getUTCFullYear() - start.getUTCFullYear()) * 12 + now.getUTCMonth() - start.getUTCMonth() : now.getUTCFullYear() - start.getUTCFullYear());
  if (occurrenceDate(schedule.anchorDate, schedule.frequency, index) < today) index++;
  return occurrenceDate(schedule.anchorDate, schedule.frequency, index);
}

export function nextCustomerSchedule(schedules: InvoiceSchedule[], customerId: string, today = todayIso()) {
  return schedules.filter(schedule => schedule.customerId === customerId && schedule.status === "active").sort((a, b) => nextOccurrence(a, today).localeCompare(nextOccurrence(b, today)))[0];
}
