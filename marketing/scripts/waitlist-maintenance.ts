import { waitlistDeps } from "../lib/waitlist/runtime";
import { maintainWaitlist } from "../lib/waitlist/service";

// Manual recovery only. Supabase Cron owns scheduled retention and reminders.
// It logs counts only. Launch notices are never part of this job.
const deps = waitlistDeps();
if (!deps) {
  console.error(JSON.stringify({ event: "waitlist_maintenance_unavailable" }));
  process.exitCode = 1;
} else {
  try {
    const result = await maintainWaitlist(deps);
    if (result.remindersFailed) process.exitCode = 1;
  } catch {
    console.error(JSON.stringify({ event: "waitlist_maintenance_failed" }));
    process.exitCode = 1;
  }
}
