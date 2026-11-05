import { describe, expect, test } from "bun:test";
import { matchesWorkspaceShortcut, workspaceShortcutKeys, workspaceShortcutMatchesQuery, workspaceKeyboardTargetBlocked, type WorkspaceKeyboardShortcut } from "../lib/keyboard-shortcuts";
const approve: WorkspaceKeyboardShortcut = { id: "approve", label: "Aprobar", code: "Enter", keyLabel: "Enter", shift: true };
const key = (overrides = {}) => ({ key: "Enter", code: "Enter", metaKey: true, ctrlKey: false, shiftKey: true, altKey: false, repeat: false, ...overrides });
describe("workspace shortcut boundaries", () => {
  test("matches physical keys only with exactly the platform chord", () => {
    expect(matchesWorkspaceShortcut(approve, key({ key: "Unidentified" }), true)).toBe(true);
    for (const extra of [{ repeat: true }, { altKey: true }, { ctrlKey: true }, { shiftKey: false }, { metaKey: false }, { code: "KeyW" }]) expect(matchesWorkspaceShortcut(approve, key(extra), true)).toBe(false);
    expect(matchesWorkspaceShortcut(approve, key({ metaKey: false, ctrlKey: true }), false)).toBe(true);
    expect(matchesWorkspaceShortcut(approve, key(), false)).toBe(false);
  });
  test("jump numbers reuse the registry and show only the selected platform", () => {
    const jump = { ...approve, jumpIndex: 1 };
    expect(matchesWorkspaceShortcut(jump, key({ code: "Digit2", altKey: true, shiftKey: false }), true)).toBe(true);
    expect(matchesWorkspaceShortcut(jump, key({ code: "Digit2", metaKey: false, ctrlKey: true }), false)).toBe(true);
    expect(workspaceShortcutKeys(jump, true)).toEqual(["⌘", "⌥", "2"]);
    expect(workspaceShortcutKeys(jump, false)).toEqual(["Ctrl", "Shift", "2"]);
  });
  test("composition, typing, handled keys, and repeats never reach an action", () => {
    const event = { ...key(), defaultPrevented: false, isComposing: false, keyCode: 13, target: null };
    expect(workspaceKeyboardTargetBlocked(event as unknown as KeyboardEvent)).toBe(false);
    for (const blocked of [{ isComposing: true }, { keyCode: 229 }, { repeat: true }, { defaultPrevented: true }, { target: { closest: () => ({}) } }]) expect(workspaceKeyboardTargetBlocked({ ...event, ...blocked } as unknown as KeyboardEvent)).toBe(true);
  });
});

test("shortcut search accepts the label and typed modifier names", () => {
  expect(workspaceShortcutMatchesQuery(approve, true, "cmd shift enter")).toBe(true);
  expect(workspaceShortcutMatchesQuery(approve, true, "⌘⇧Enter")).toBe(true);
  expect(workspaceShortcutMatchesQuery(approve, false, "control+shift+enter")).toBe(true);
  expect(workspaceShortcutMatchesQuery(approve, true, "aprobar")).toBe(true);
  expect(workspaceShortcutMatchesQuery(approve, true, "cmd+w")).toBe(false);
});

import { clearTitleFocusUnless, handTitleFocus, takeTitleFocus } from "../components/business-app/bandeja-order";
test("navigation clears abandoned title focus but retains the intended receipt", () => {
  handTitleFocus("next");
  clearTitleFocusUnless("next");
  expect(takeTitleFocus("next")).toBe(true);
  expect(takeTitleFocus("next")).toBe(false);
  handTitleFocus("next");
  clearTitleFocusUnless("other");
  expect(takeTitleFocus("next")).toBe(false);
  handTitleFocus("next");
  clearTitleFocusUnless();
  expect(takeTitleFocus("next")).toBe(false);
});
