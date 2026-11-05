import { describe, expect, test } from "bun:test";
import type { RecoveryDisplay } from "../lib/chat-recovery-display";
import { createDailyCapNoticeState, DAILY_CAP_NOTICE_STORAGE_KEY } from "../lib/daily-cap-notice-state";
import { DAILY_CAP_RECOVERY_CODE } from "../lib/daily-cap-reset-time";
import { STORAGE_REGISTRY } from "../lib/browser-storage";

const receivedAt = Date.parse("2026-09-26T18:00:00Z");
const resetsAt = Date.parse("2026-09-27T00:00:00Z");
const accountId = "account-alpha";
const otherAccountId = "account-beta";
const display = (resetAt = resetsAt): RecoveryDisplay => ({
  kind: "recovery_code", code: DAILY_CAP_RECOVERY_CODE,
  values: { resetAt: new Date(resetAt).toISOString() },
});

function fixture(initial: unknown = null) {
  let saved = initial === null ? null : JSON.stringify(initial);
  let now = receivedAt;
  const storage = {
    read: () => saved,
    write: (value: string) => { saved = value; },
    remove: () => { saved = null; },
  };
  const create = () => createDailyCapNoticeState(storage, () => now);
  return { state: create(), create, saved: () => saved, advance: (at: number) => { now = at; } };
}

describe("daily cap notice lifecycle", () => {
  test("an older successful question cannot clear a newer rejection from another chat", () => {
    const { state } = fixture();
    state.setAccount(accountId);
    state.record(accountId, display());
    const observedAtSend = state.getSnapshot();
    state.record(accountId, display());
    const newerRejection = state.getSnapshot();
    state.clear(accountId, observedAtSend);
    expect(state.getSnapshot()).toBe(newerRejection);
    state.clear(accountId, newerRejection);
    expect(state.getSnapshot()).toBeNull();
  });

  test("an authorized dispatcher created before bootstrap uses the established account", () => {
    const { state } = fixture();
    const record = (recovery: RecoveryDisplay) => state.record(state.getAccount(), recovery);
    const clear = () => state.clear(state.getAccount());
    expect(state.getAccount()).toBeUndefined();
    state.setAccount(accountId);
    expect(record(display())).toBe(true);
    expect(state.getSnapshot()?.accountId).toBe(accountId);
    clear();
    expect(state.getSnapshot()).toBeNull();
  });

  test("keeps one account-scoped notice and resurfaces it on a fresh rejection", () => {
    const { state, saved } = fixture();
    state.setAccount(accountId);
    expect(state.record(accountId, display())).toBe(true);
    expect(state.getSnapshot()).toEqual({ accountId, resetAt: resetsAt, dismissed: false });
    state.dismiss(accountId, resetsAt);
    expect(state.getSnapshot()?.dismissed).toBe(true);
    state.record(accountId, display());
    expect(state.getSnapshot()?.dismissed).toBe(false);
    const revisedReset = resetsAt + 60_000;
    state.record(accountId, display(revisedReset));
    // A close handler from the previous notice cannot dismiss its replacement.
    state.dismiss(accountId, resetsAt);
    expect(JSON.parse(saved()!)).toEqual({ accountId, resetAt: revisedReset, dismissed: false });
    expect(STORAGE_REGISTRY[DAILY_CAP_NOTICE_STORAGE_KEY]).toBe("temporary");
  });

  test.each([false, true])("reload restores the same reset window with dismissed=%s", (dismissed) => {
    const { state, create, saved } = fixture();
    state.setAccount(accountId);
    state.record(accountId, display());
    if (dismissed) state.dismiss(accountId, resetsAt);
    const reloaded = create();
    reloaded.setAccount(undefined);
    expect(saved()).not.toBeNull();
    reloaded.setAccount(accountId);
    expect(reloaded.getSnapshot()).toEqual({ accountId, resetAt: resetsAt, dismissed });
  });

  test("expiry clears visible or dismissed metadata at the same deadline", () => {
    for (const dismissed of [false, true]) {
      const { state, saved, advance } = fixture();
      state.setAccount(accountId);
      state.record(accountId, display());
      if (dismissed) state.dismiss(accountId, resetsAt);
      advance(resetsAt - 1);
      state.expire(accountId);
      expect(state.getSnapshot()).not.toBeNull();
      advance(resetsAt);
      state.expire(accountId);
      expect(state.getSnapshot()).toBeNull();
      expect(saved()).toBeNull();
    }
  });

  test("account switch and logout clear the old observation and ignore its callbacks", () => {
    const { state, saved } = fixture();
    state.setAccount(accountId);
    state.record(accountId, display());
    state.setAccount(otherAccountId);
    expect(state.getSnapshot()).toBeNull();
    expect(saved()).toBeNull();
    expect(state.record(accountId, display())).toBe(true);
    expect(state.getSnapshot()).toBeNull();
    state.record(otherAccountId, display());
    state.clear(accountId);
    state.dismiss(accountId, resetsAt);
    expect(state.getSnapshot()).toEqual({ accountId: otherAccountId, resetAt: resetsAt, dismissed: false });
    state.setAccount(undefined);
    expect(state.getSnapshot()).toBeNull();
    state.record(otherAccountId, display());
    expect(saved()).toBeNull();
  });

  test("loading another account never adopts a previous account's saved notice", () => {
    const { state, saved } = fixture({ accountId, resetAt: resetsAt, dismissed: false });
    state.setAccount(undefined);
    expect(saved()).not.toBeNull();
    state.setAccount(otherAccountId);
    expect(state.getSnapshot()).toBeNull();
    expect(saved()).toBeNull();
  });

  test("successful completion clears the observation; unmounted callbacks cannot restore it", () => {
    const { state, saved, create, advance } = fixture();
    state.setAccount(accountId);
    state.record(accountId, display());
    state.clear(accountId);
    expect(saved()).toBeNull();
    state.record(accountId, display());
    state.suspend();
    state.record(accountId, display(resetsAt + 60_000));
    state.clear(accountId);
    expect(state.getSnapshot()?.resetAt).toBe(resetsAt);
    // Navigation unmount preserves the record for a new hook instance.
    expect(saved()).not.toBeNull();
    const next = create();
    next.setAccount(otherAccountId);
    next.record(otherAccountId, display(resetsAt + 60_000));
    advance(resetsAt);
    state.expire(accountId);
    expect(JSON.parse(saved()!).accountId).toBe(otherAccountId);
  });

  test("recognizes only the typed cap and rejects invalid or expired reset values", () => {
    const { state } = fixture();
    state.setAccount(accountId);
    expect(state.record(accountId, null)).toBe(false);
    expect(state.record(accountId, { kind: "recovery_code", code: "too_many_requests" })).toBe(false);
    for (const resetAt of [undefined, "tomorrow", "", new Date(receivedAt).toISOString()]) {
      expect(state.record(accountId, {
        kind: "recovery_code", code: DAILY_CAP_RECOVERY_CODE,
        ...(resetAt === undefined ? {} : { values: { resetAt } }),
      })).toBe(true);
      expect(state.getSnapshot()).toBeNull();
    }
  });

  test.each([
    "not an object", [], {},
    { accountId: "", resetAt: resetsAt, dismissed: false },
    { accountId, resetAt: "2026-09-27T00:00:00Z", dismissed: false },
    { accountId, resetAt: receivedAt, dismissed: false },
    { accountId, resetAt: 9e15, dismissed: false },
    { accountId, resetAt: resetsAt, dismissed: "false" },
  ].map((saved) => [saved]))("discards malformed or expired saved state: %j", (saved) => {
    const fixtureState = fixture(saved);
    expect(fixtureState.state.getSnapshot()).toBeNull();
    expect(fixtureState.saved()).toBeNull();
  });

  test("discards unreadable JSON without throwing", () => {
    let removed = false;
    const state = createDailyCapNoticeState({
      read: () => "{",
      write: () => {},
      remove: () => { removed = true; },
    }, () => receivedAt);
    expect(state.getSnapshot()).toBeNull();
    expect(removed).toBe(true);
  });

  test("blocked storage never prevents the in-memory notice lifecycle", () => {
    const blocked = () => { throw new Error("Storage blocked"); };
    const state = createDailyCapNoticeState({ read: blocked, write: blocked, remove: blocked }, () => receivedAt);
    state.setAccount(accountId);
    state.record(accountId, display());
    expect(state.getSnapshot()?.resetAt).toBe(resetsAt);
    state.dismiss(accountId, resetsAt);
    expect(state.getSnapshot()?.dismissed).toBe(true);
    state.clear(accountId);
    expect(state.getSnapshot()).toBeNull();
  });
});
