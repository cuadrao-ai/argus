import { todayIso, type Period } from "../business-format";
import { receptionSentBy, type ReceptionRow, type ReceptionSource } from "./reception-model";

/** Canal and Enviado por only: the tabs own status. `senders` holds the server's `sent_by.id`. */
export type ReceptionFiltersValue = { channels: ReceptionSource[]; senders: string[] };
/** One sender the filter offers: the server's id and the words the screen shows for it. */
export type SenderOption = { id: string; name: string };
export const emptyReceptionFilters = (): ReceptionFiltersValue => ({ channels: [], senders: [] });

export function receptionFilterMatches(row: ReceptionRow, filters: ReceptionFiltersValue): boolean {
  const sender = receptionSentBy(row);
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
