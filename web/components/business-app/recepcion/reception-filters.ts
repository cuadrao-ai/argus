import { todayIso, type Period } from "../business-format";
import { receptionSender, type ReceptionRow, type ReceptionSource } from "./reception-model";

/** Canal and Remitente only: the tabs own status. */
export type ReceptionFiltersValue = { channels: ReceptionSource[]; senders: string[] };
export type SenderIdentity = { id: string; name: string | null; address: string };
export const emptyReceptionFilters = (): ReceptionFiltersValue => ({ channels: [], senders: [] });

/** A known sender address is the current contract's identity, never the search input or merchant. */
export function receptionSenderIdentity(row: ReceptionRow): SenderIdentity | null {
  const raw = receptionSender(row)?.trim();
  if (!raw) return null;
  const named = /^(.*?)\s*<([^<>]+)>$/.exec(raw);
  const address = named ? named[2].trim() : raw;
  const name = named?.[1].trim().replace(/^"|"$/g, "") || null;
  return { id: `${row.source}:${address.toLocaleLowerCase()}`, name, address };
}

export function receptionFilterMatches(row: ReceptionRow, filters: ReceptionFiltersValue): boolean {
  const sender = receptionSenderIdentity(row);
  return (!filters.channels.length || filters.channels.includes(row.source))
    && (!filters.senders.length || !!sender && filters.senders.includes(sender.id));
}

/** Arrival timestamp in the same local calendar used by the existing date control. */
export function receptionArrivedInPeriod(row: ReceptionRow, period: Period): boolean {
  if (period.key === "all") return true;
  const timestamp = new Date(row.receivedAt);
  if (Number.isNaN(timestamp.getTime())) return false;
  const day = todayIso(timestamp);
  return day >= period.from && day <= (period.to ?? todayIso());
}
