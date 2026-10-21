import type { WaitlistStore } from "./types.ts";
import type { waitlistMail } from "./email.ts";

export async function remindWaitlist(deps: { store: WaitlistStore; send: ReturnType<typeof waitlistMail> }, limit = 100) {
  const rows = await deps.store.reminders(limit);
  let sent = 0;
  let failed = 0;
  for (const row of rows) {
    // Read again so a confirmed or deleted row does not get a queued reminder.
    const active = await deps.store.find(row.verification_id.slice(0, 32));
    if (!active || active.confirmed_at) continue;
    const outcome = await deps.send("reminder", row);
    if (outcome === "sent") sent += 1;
    else {
      failed += 1;
      if (outcome === "refused") await deps.store.release(row.verification_id, row.last_confirmation_sent_at!, true);
    }
  }
  return { remindersSent: sent, remindersFailed: failed };
}
