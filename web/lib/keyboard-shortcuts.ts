export type KeyboardShortcutId =
  | "omnisearch"
  | "keyboard_shortcuts"
  | "new_chat"
  | "open_recents"
  | "delete_focused_chat"
  | "rename_focused_chat"
  | "archive_focused_chat"
  | "toggle_read_focused_chat"
  | "expand_sidebar_recents"
  | "open_settings"
  | "toggle_pin_focused_chat"
  | "quick_jump"
  | "command_palette_rename"
  | "command_palette_archive"
  | "command_palette_delete";

export type KeyboardShortcutGroup =
  | "navigation"
  | "chat"
  | "quick_jump"
  | "omnisearch";

export type KeyboardShortcutEvent = Pick<
  KeyboardEvent,
  "altKey" | "code" | "ctrlKey" | "key" | "metaKey" | "repeat" | "shiftKey"
>;

export type KeyboardDeleteRequest = {
  conversationId: string;
  showKeyboardHints: boolean;
};

type KeyboardShortcutMatch =
  | "primary_key"
  | "primary_shift_key"
  | "primary_shift_code"
  | "shift_code"
  | "code"
  | "quick_jump";

export type KeyboardShortcutDefinition = {
  id: KeyboardShortcutId;
  group: KeyboardShortcutGroup;
  /** Acts on conversations, so a workspace without chat neither offers nor lists it. */
  needsChat: boolean;
  labelKey: string;
  defaultLabel: string;
  match: KeyboardShortcutMatch;
  key?: string;
  code?: string;
  macDisplay: readonly string[];
  otherDisplay: readonly string[];
};

export const KEYBOARD_SHORTCUTS: readonly KeyboardShortcutDefinition[] = [
  {
    id: "omnisearch",
    group: "navigation",
    needsChat: false,
    labelKey: "keyboard_shortcuts.shortcuts.omnisearch",
    defaultLabel: "Open search",
    match: "primary_key",
    key: "k",
    macDisplay: ["⌘", "K"],
    otherDisplay: ["Ctrl", "K"],
  },
  {
    id: "keyboard_shortcuts",
    group: "navigation",
    needsChat: false,
    labelKey: "keyboard_shortcuts.shortcuts.keyboard_shortcuts",
    defaultLabel: "Show keyboard shortcuts",
    match: "primary_key",
    key: "/",
    macDisplay: ["⌘", "/"],
    otherDisplay: ["Ctrl", "/"],
  },
  {
    id: "open_recents",
    group: "navigation",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.open_recents",
    defaultLabel: "Open Recents",
    match: "primary_shift_code",
    code: "Comma",
    macDisplay: ["⌘", "Shift", ","],
    otherDisplay: ["Ctrl", "Shift", ","],
  },
  {
    id: "expand_sidebar_recents",
    group: "navigation",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.expand_sidebar_recents",
    defaultLabel: "Toggle sidebar and Recents",
    match: "primary_shift_code",
    code: "Backslash",
    macDisplay: ["⌘", "Shift", "\\"],
    otherDisplay: ["Ctrl", "Shift", "\\"],
  },
  {
    id: "open_settings",
    group: "navigation",
    needsChat: false,
    labelKey: "keyboard_shortcuts.shortcuts.open_settings",
    defaultLabel: "Open Settings",
    match: "primary_shift_code",
    code: "Semicolon",
    macDisplay: ["⌘", "Shift", ";"],
    otherDisplay: ["Ctrl", "Shift", ";"],
  },
  {
    id: "new_chat",
    group: "chat",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.new_chat",
    defaultLabel: "New chat",
    match: "primary_shift_code",
    code: "Period",
    macDisplay: ["⌘", "Shift", "."],
    otherDisplay: ["Ctrl", "Shift", "."],
  },
  {
    id: "delete_focused_chat",
    group: "chat",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.delete_focused_chat",
    defaultLabel: "Delete current chat",
    match: "primary_shift_key",
    key: "d",
    macDisplay: ["⌘", "Shift", "D"],
    otherDisplay: ["Ctrl", "Shift", "D"],
  },
  {
    id: "rename_focused_chat",
    group: "chat",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.rename_focused_chat",
    defaultLabel: "Rename current chat",
    match: "primary_shift_key",
    key: "r",
    macDisplay: ["⌘", "Shift", "R"],
    otherDisplay: ["Ctrl", "Shift", "R"],
  },
  {
    id: "archive_focused_chat",
    group: "chat",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.archive_focused_chat",
    defaultLabel: "Archive current chat",
    match: "primary_shift_key",
    key: "a",
    macDisplay: ["⌘", "Shift", "A"],
    otherDisplay: ["Ctrl", "Shift", "A"],
  },
  {
    id: "toggle_read_focused_chat",
    group: "chat",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.toggle_read_focused_chat",
    defaultLabel: "Mark current chat as read or unread",
    match: "primary_shift_key",
    key: "u",
    macDisplay: ["⌘", "Shift", "U"],
    otherDisplay: ["Ctrl", "Shift", "U"],
  },
  {
    id: "toggle_pin_focused_chat",
    group: "chat",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.toggle_pin_focused_chat",
    defaultLabel: "Pin or unpin current chat",
    match: "primary_shift_code",
    code: "Quote",
    macDisplay: ["⌘", "Shift", "'"],
    otherDisplay: ["Ctrl", "Shift", "'"],
  },
  {
    id: "quick_jump",
    group: "quick_jump",
    needsChat: true,
    labelKey: "keyboard_shortcuts.shortcuts.quick_jump",
    defaultLabel: "Quick-jump visible items",
    match: "quick_jump",
    macDisplay: ["⌘", "⌥", "1–9"],
    otherDisplay: ["Ctrl", "Shift", "1–9"],
  },
  {
    id: "command_palette_rename",
    group: "omnisearch",
    needsChat: true,
    labelKey: "command_palette.shortcut_legend.rename",
    defaultLabel: "Rename",
    match: "primary_shift_key",
    key: "r",
    macDisplay: ["⌘", "Shift", "R"],
    otherDisplay: ["Ctrl", "Shift", "R"],
  },
  {
    id: "command_palette_archive",
    group: "omnisearch",
    needsChat: true,
    labelKey: "command_palette.shortcut_legend.archive",
    defaultLabel: "Archive",
    match: "primary_shift_key",
    key: "a",
    macDisplay: ["⌘", "Shift", "A"],
    otherDisplay: ["Ctrl", "Shift", "A"],
  },
  {
    id: "command_palette_delete",
    group: "omnisearch",
    needsChat: true,
    labelKey: "command_palette.shortcut_legend.delete",
    defaultLabel: "Delete",
    match: "primary_shift_key",
    key: "d",
    macDisplay: ["⌘", "Shift", "D"],
    otherDisplay: ["Ctrl", "Shift", "D"],
  },
];

function keyboardShortcut(id: KeyboardShortcutId): KeyboardShortcutDefinition {
  const shortcut = KEYBOARD_SHORTCUTS.find((item) => item.id === id);
  if (!shortcut) {
    throw new Error(`Unknown keyboard shortcut: ${id}`);
  }
  return shortcut;
}

function hasPrimaryModifier(event: KeyboardShortcutEvent): boolean {
  return event.metaKey || event.ctrlKey;
}

export function matchesKeyboardShortcut(
  id: KeyboardShortcutId,
  event: KeyboardShortcutEvent,
): boolean {
  if (event.repeat) return false;
  const shortcut = keyboardShortcut(id);
  if (shortcut.match === "quick_jump") return false;

  if (shortcut.match === "primary_key") {
    return (
      hasPrimaryModifier(event) &&
      event.key.toLowerCase() === shortcut.key?.toLowerCase()
    );
  }

  if (shortcut.match === "primary_shift_key") {
    return (
      hasPrimaryModifier(event) &&
      event.shiftKey &&
      !event.altKey &&
      event.key.toLowerCase() === shortcut.key?.toLowerCase()
    );
  }

  if (shortcut.match === "primary_shift_code") {
    return (
      hasPrimaryModifier(event) &&
      event.shiftKey &&
      !event.altKey &&
      event.code === shortcut.code
    );
  }

  if (shortcut.match === "shift_code") {
    return (
      event.shiftKey &&
      !event.altKey &&
      !event.ctrlKey &&
      !event.metaKey &&
      event.code === shortcut.code
    );
  }

  return (
    event.code === shortcut.code &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey
  );
}

export type CommandPaletteRowAction = "rename" | "archive" | "delete";

const COMMAND_PALETTE_ROW_ACTIONS: ReadonlyArray<
  readonly [KeyboardShortcutId, CommandPaletteRowAction]
> = [
  ["command_palette_rename", "rename"],
  ["command_palette_archive", "archive"],
  ["command_palette_delete", "delete"],
];

export function commandPaletteRowActionForEvent(
  event: KeyboardShortcutEvent,
): CommandPaletteRowAction | null {
  for (const [shortcutId, action] of COMMAND_PALETTE_ROW_ACTIONS) {
    if (matchesKeyboardShortcut(shortcutId, event)) return action;
  }
  return null;
}

export function keyboardShortcutDisplay(
  id: KeyboardShortcutId,
  usesCommandKey: boolean,
): readonly string[] {
  const shortcut = keyboardShortcut(id);
  return usesCommandKey
    ? shortcut.macDisplay.map((key) => (key === "Shift" ? "⇧" : key))
    : shortcut.otherDisplay;
}

export function keyboardShortcutHintDisplay(
  id: KeyboardShortcutId,
  usesCommandKey: boolean,
): string {
  const keys = keyboardShortcutDisplay(id, usesCommandKey);
  if (!usesCommandKey) {
    return keys
      .map((key) => (key === "Shift" ? "⇧" : key))
      .join("+")
      .replace("+⇧+", "⇧");
  }

  return keys
    .map((key) => {
      if (key === "Shift") return "⇧";
      if (key === "Alt") return "⌥";
      if (key === "Ctrl") return "⌃";
      return key;
    })
    .join("");
}

export function quickJumpHintDisplay(
  number: number,
  usesCommandKey: boolean,
): string {
  return usesCommandKey ? `⌘⌥${number}` : `Ctrl+Shift+${number}`;
}

export function isKeyboardShortcutHintModifierActive(
  event: KeyboardShortcutEvent,
  usesCommandKey: boolean,
): boolean {
  if (usesCommandKey) return event.metaKey && !event.ctrlKey;
  return event.ctrlKey && !event.metaKey && !event.altKey;
}

export function isQuickJumpModifierActive(
  event: KeyboardShortcutEvent,
  usesCommandKey: boolean,
): boolean {
  if (usesCommandKey) {
    return event.metaKey && !event.ctrlKey;
  }
  return event.ctrlKey && event.shiftKey && !event.metaKey && !event.altKey;
}

export function quickJumpIndexForEvent(
  event: KeyboardShortcutEvent,
  usesCommandKey: boolean,
): number | null {
  if (event.repeat) return null;
  const modifierMatches = usesCommandKey
    ? event.metaKey && event.altKey && !event.ctrlKey && !event.shiftKey
    : event.ctrlKey && event.shiftKey && !event.metaKey && !event.altKey;
  const match = /^Digit([1-9])$/.exec(event.code);
  return modifierMatches && match ? Number(match[1]) - 1 : null;
}


export type WorkspaceKeyboardShortcut = Readonly<{
  id: string;
  label: string;
  code: string;
  keyLabel: string;
  shift?: boolean;
  jumpIndex?: number;
  run?: () => boolean;
}>;

export function matchesWorkspaceShortcut(shortcut: WorkspaceKeyboardShortcut, event: KeyboardShortcutEvent, command: boolean): boolean {
  if (event.repeat) return false;
  if (shortcut.jumpIndex !== undefined) return quickJumpIndexForEvent(event, command) === shortcut.jumpIndex;
  const primary = command ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  return primary && !event.altKey && event.shiftKey === Boolean(shortcut.shift) && event.code === shortcut.code;
}

export function workspaceShortcutKeys(shortcut: WorkspaceKeyboardShortcut, command: boolean): readonly string[] {
  if (shortcut.jumpIndex !== undefined) return command ? ["⌘", "⌥", String(shortcut.jumpIndex + 1)] : ["Ctrl", "Shift", String(shortcut.jumpIndex + 1)];
  return [command ? "⌘" : "Ctrl", ...(shortcut.shift ? [command ? "⇧" : "Shift"] : []), shortcut.keyLabel];
}

export function workspaceKeyboardTargetBlocked(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  return event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229 || Boolean(target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]'));
}

export function workspaceShortcutMatchesQuery(shortcut: WorkspaceKeyboardShortcut, command: boolean, query: string): boolean {
  const normalize = (value: string) => value.toLocaleLowerCase().replace(/⌘|command|cmd/g, "meta").replace(/⌥|option/g, "alt").replace(/⇧/g, "shift").replace(/control/g, "ctrl").replace(/[+\s]/g, "");
  return normalize(`${shortcut.label} ${workspaceShortcutKeys(shortcut, command).join(" ")} ${shortcut.code}`).includes(normalize(query));
}
