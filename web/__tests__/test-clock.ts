import { setSystemTime } from "bun:test";

/**
 * The instant every test starts from. Sample records are dated by days back
 * from today, and the default period is the month that contains today, so a
 * suite on the wall clock passes or fails with the date it runs on. Midday UTC
 * keeps the local calendar day the same in every time zone from UTC-12 to UTC+11.
 */
export const TEST_NOW = new Date("2026-10-31T12:00:00Z");

export function pinTestClock(): void {
  setSystemTime(TEST_NOW);
}
