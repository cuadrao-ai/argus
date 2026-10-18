import { z } from "zod";
import { readStored, removeStored, writeStored } from "./browser-storage";

const STORAGE_KEY = "cuadrao-age-confirmed-at";
const CHANGE_EVENT = "cuadrao-age-confirmation";
const timestamp = z.iso.datetime({ offset: true });
let memoryConfirmation: string | null = null;

export function readAgeConfirmation(): string | null {
  if (typeof window === "undefined") return memoryConfirmation;
  const raw = readStored(STORAGE_KEY) ?? memoryConfirmation;
  const parsed = timestamp.safeParse(raw);
  if (!parsed.success || Date.parse(parsed.data) > Date.now() + 5 * 60_000) return null;
  return parsed.data;
}

export function confirmAge(): string {
  const confirmedAt = readAgeConfirmation() ?? new Date().toISOString();
  memoryConfirmation = confirmedAt;
  if (typeof window !== "undefined") {
    writeStored(STORAGE_KEY, confirmedAt);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
  return confirmedAt;
}

export function requireAgeConfirmation(): string {
  const confirmedAt = readAgeConfirmation();
  if (!confirmedAt) throw Object.assign(new Error("age_confirmation_required"), { code: "age_confirmation_required" });
  return confirmedAt;
}

export function subscribeAgeConfirmation(listener: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(CHANGE_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}

export function resetAgeConfirmationForTests() {
  memoryConfirmation = null;
  if (typeof window !== "undefined") {
    removeStored(STORAGE_KEY);
  }
}
