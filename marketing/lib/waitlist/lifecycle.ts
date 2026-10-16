export type WaitlistLifecycle = {
  signedUpAt: Date;
  confirmedAt: Date | null;
  lastConfirmationAt: Date | null;
  reminderAt: Date | null;
};

export type ScheduledWaitlistAction = "delete" | "remind" | "none";

const HOUR = 60 * 60 * 1000;

export function confirmationExpired(issuedAt: Date, now: Date): boolean {
  return now.getTime() >= issuedAt.getTime() + 48 * HOUR;
}

export function confirmationAllowed(state: WaitlistLifecycle, now: Date): boolean {
  return state.confirmedAt === null && (state.lastConfirmationAt === null
    || now.getTime() >= state.lastConfirmationAt.getTime() + 10 * 60 * 1000);
}

export function retentionDeadline(state: WaitlistLifecycle): Date {
  if (state.confirmedAt === null) return new Date(state.signedUpAt.getTime() + 7 * 24 * HOUR);
  const deadline = new Date(state.signedUpAt);
  const day = deadline.getUTCDate();
  deadline.setUTCDate(1);
  deadline.setUTCFullYear(deadline.getUTCFullYear() + 1);
  const lastDay = new Date(Date.UTC(deadline.getUTCFullYear(), deadline.getUTCMonth() + 1, 0)).getUTCDate();
  deadline.setUTCDate(Math.min(day, lastDay));
  return deadline;
}

export function scheduledAction(state: WaitlistLifecycle, now: Date): ScheduledWaitlistAction {
  if (now >= retentionDeadline(state)) return "delete";
  if (state.confirmedAt === null && state.reminderAt === null
    && now.getTime() >= state.signedUpAt.getTime() + 24 * HOUR
    && confirmationAllowed(state, now)) return "remind";
  return "none";
}
