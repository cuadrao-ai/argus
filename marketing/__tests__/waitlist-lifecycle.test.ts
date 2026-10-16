import { expect, test } from "bun:test";
import { confirmationAllowed, confirmationExpired, retentionDeadline, scheduledAction, type WaitlistLifecycle } from "../lib/waitlist/lifecycle";

const pending: WaitlistLifecycle = {
  signedUpAt: new Date("2026-10-16T12:00:00Z"),
  confirmedAt: null,
  lastConfirmationAt: new Date("2026-10-16T12:00:00Z"),
  reminderAt: null,
};

test("a confirmation expires at exactly 48 hours", () => {
  expect(confirmationExpired(pending.signedUpAt, new Date("2026-10-18T11:59:59.999Z"))).toBe(false);
  expect(confirmationExpired(pending.signedUpAt, new Date("2026-10-18T12:00:00Z"))).toBe(true);
});

test("confirmation sends are at least 10 minutes apart", () => {
  expect(confirmationAllowed(pending, new Date("2026-10-16T12:09:59.999Z"))).toBe(false);
  expect(confirmationAllowed(pending, new Date("2026-10-16T12:10:00Z"))).toBe(true);
  expect(confirmationAllowed({ ...pending, confirmedAt: new Date("2026-10-16T12:01:00Z") }, new Date("2026-10-17T12:00:00Z"))).toBe(false);
});

test("one reminder becomes due after 24 hours and never after retention", () => {
  expect(scheduledAction(pending, new Date("2026-10-17T11:59:59.999Z"))).toBe("none");
  expect(scheduledAction(pending, new Date("2026-10-17T12:00:00Z"))).toBe("remind");
  expect(scheduledAction({ ...pending, reminderAt: new Date("2026-10-17T12:00:00Z") }, new Date("2026-10-18T12:00:00Z"))).toBe("none");
  expect(scheduledAction(pending, new Date("2026-10-23T12:00:00Z"))).toBe("delete");
});

test("retention starts at signup and uses calendar months for confirmed people", () => {
  expect(retentionDeadline(pending).toISOString()).toBe("2026-10-23T12:00:00.000Z");
  expect(retentionDeadline({ ...pending, confirmedAt: new Date("2026-10-17T14:00:00Z") }).toISOString()).toBe("2027-10-16T12:00:00.000Z");
  expect(retentionDeadline({ ...pending, signedUpAt: new Date("2024-02-29T12:30:00Z"), confirmedAt: new Date("2024-03-01T12:00:00Z") }).toISOString()).toBe("2025-02-28T12:30:00.000Z");
});
