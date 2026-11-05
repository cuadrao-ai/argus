import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  RECEIPT_OWNER_NOTE_MAX_LENGTH,
  receiptFailureReason,
  receiptUrl,
  type EvidenceReceipt,
} from "../lib/evidence-receipts";
import { evidenceReceiptSharingEnabled } from "../lib/private-alpha-flags";

const WEB_ROOT = join(import.meta.dir, "..");
const SHARE_ACTION = join(WEB_ROOT, "components/chat/ShareReceiptAction.tsx");
const RECEIPT_LIST = join(WEB_ROOT, "components/settings/SharedReceiptsView.tsx");
const CHAT_HEADER = join(WEB_ROOT, "components/chat/ChatHeaderMenu.tsx");
const PROFILE_MENU = join(WEB_ROOT, "components/sidebar/ProfileMenu.tsx");
const PANEL_REGISTRY = join(
  WEB_ROOT,
  "components/sidebar/ProfileSettingsPanels.tsx",
);

function source(path: string): string {
  return readFileSync(path, "utf8");
}

const RECEIPT: EvidenceReceipt = {
  kind: "backtest",
  id: "receipt-1",
  public_id: "abcdefghijklmnopqrstuvwx",
  path: "/r/abcdefghijklmnopqrstuvwx",
  title: "AAPL buy and hold",
  symbols: ["AAPL"],
  date_range: { start: "2024-01-02", end: "2024-03-01" },
  created_at: "2026-08-07T12:00:00Z",
  revoked_at: null,
  revocation_reason: null,
};

describe("the sharing flag", () => {
  test("is off unless the environment says exactly true", () => {
    // The lane must not enable itself by landing.
    expect(evidenceReceiptSharingEnabled).toBe(false);
    const flags = source(join(WEB_ROOT, "lib/private-alpha-flags.ts"));
    expect(flags).toContain(
      'process.env.NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED === "true"',
    );
  });

  test("gates every owner surface", () => {
    expect(source(CHAT_HEADER)).toContain("evidenceReceiptSharingEnabled &&");
    expect(source(PROFILE_MENU)).toContain("evidenceReceiptSharingEnabled");
  });

  test("hides the receipt list from guests, not just behind the flag", () => {
    // Every owner endpoint needs the registered-only can_save_decision, so a
    // guest opening this gets a modal whose only action is a retry that cannot
    // succeed.
    const menu = source(PROFILE_MENU);
    expect(menu).toContain(
      'evidenceReceiptSharingEnabled && accountKind === "registered"',
    );
    // Ajustes lists the section only through that same gate.
    expect(menu).toContain("receipts: receiptsAvailable,");
  });
});

describe("receipt urls", () => {
  test("compose from the current origin, so the backend owns no origin config", () => {
    expect(receiptUrl(RECEIPT)).toBe(RECEIPT.path);
    expect(source(join(WEB_ROOT, "lib/evidence-receipts.ts"))).toContain(
      "window.location.origin",
    );
  });

  test("fall back to the public id when the server omits a path", () => {
    expect(receiptUrl({ ...RECEIPT, path: "" })).toBe(
      `/r/${RECEIPT.public_id}`,
    );
  });
});

describe("failure reasons", () => {
  test("map the note rejection, the rate limit, and everything else", () => {
    expect(receiptFailureReason({ code: "receipt_note_rejected" })).toBe(
      "note_rejected",
    );
    expect(receiptFailureReason({ status: 429 })).toBe("rate_limited");
    expect(receiptFailureReason({ status: 500 })).toBe("unavailable");
    expect(receiptFailureReason(null)).toBe("unavailable");
  });
});

describe("copy link is the primary action", () => {
  test("no native share sheet anywhere on the owner surfaces", () => {
    for (const path of [SHARE_ACTION, RECEIPT_LIST]) {
      const body = source(path);
      expect(body).not.toContain("navigator.share");
      expect(body).toContain("copyReceiptLink");
    }
  });
});

describe("the owner note", () => {
  test("is bounded in the input, matching the backend bound", () => {
    expect(RECEIPT_OWNER_NOTE_MAX_LENGTH).toBe(280);
    expect(source(SHARE_ACTION)).toContain(
      "maxLength={RECEIPT_OWNER_NOTE_MAX_LENGTH}",
    );
  });

  test("warns that it is public before the owner types into it", () => {
    const body = source(SHARE_ACTION);
    const warningIndex = body.indexOf("note_public_warning");
    const textareaIndex = body.indexOf("<textarea");
    expect(warningIndex).toBeGreaterThan(-1);
    expect(textareaIndex).toBeGreaterThan(-1);
    // Rendered directly under the field, so it is read with it, not after.
    expect(warningIndex).toBeGreaterThan(textareaIndex);
  });
});

describe("the receipt list", () => {
  test("offers revoke in one action per row", () => {
    const body = source(RECEIPT_LIST);
    expect(body).toContain("revokeEvidenceReceipt");
    expect(body).toContain("receipt.list.confirm_revoke");
  });

  test("pages instead of capping, so no live link can hide", () => {
    // A silent cap would leave older live links unreachable, and this list is
    // the only place an owner can find one to take down.
    const body = source(RECEIPT_LIST);
    expect(body).toContain("next_cursor");
    expect(body).toContain("receipt.list.load_more");
    const client = source(join(WEB_ROOT, "lib/evidence-receipts.ts"));
    expect(client).toContain("cursor=");
  });

  test("states the cached-preview limit rather than implying links vanish", () => {
    expect(source(RECEIPT_LIST)).toContain("receipt.list.cache_note");
  });

  test("shows why a receipt was revoked when the source went away", () => {
    expect(source(RECEIPT_LIST)).toContain("source_deleted");
  });

  test("names no source conversation or run", () => {
    const body = source(RECEIPT_LIST).toLowerCase();
    for (const forbidden of [
      "source_conversation",
      "source_run",
      "evidence_artifact_id",
      "owner_id",
    ]) {
      expect(body).not.toContain(forbidden);
    }
  });

  test("draws itself through the shared panel, not its own centred card", () => {
    // The panel rule lives in AdaptivePanel: sheet below the desktop stop,
    // centred dialog above it. A panel that draws its own fixed overlay renders
    // a desktop card at phone width, which is the regression the shell exists to
    // prevent, and it escapes the overlay layer stack the drawer depends on.
    // It draws through SettingsSurface, which is that panel outside Ajustes and
    // the window's pane inside it.
    const list = source(RECEIPT_LIST);
    expect(list).toContain("<SettingsSurface");
    expect(source(join(WEB_ROOT, "components/settings/SettingsSurface.tsx"))).toContain("<AdaptivePanel {...props} />");
    expect(list).not.toContain("fixed inset-0");
  });

  test("returns to Data Controls in the sheet instead of dismissing it", () => {
    // Reached from the drawer's Data Controls submenu on a phone, so it owes the
    // same back row every sibling there offers. The panel registry owns that row
    // now: an entry declares its parent submenu and the registry supplies the
    // handler, so the receipt list states "data" rather than copying a handler.
    expect(source(RECEIPT_LIST)).toContain("onBack");
    const registry = source(PANEL_REGISTRY);
    const entry = registry.slice(
      registry.indexOf("  receipts: {"),
      registry.indexOf("\n  },", registry.indexOf("  receipts: {")),
    );
    expect(entry).toContain('parent: "data"');
    expect(entry).toContain("SharedReceiptsView");
    expect(entry).toContain("onBack");
    // And the registry only offers a way back in the sheet, which is the case that
    // has one.
    expect(registry).toContain("onBack: asSheet ? () => onBack(parent) : undefined");
  });

  test("the menu opens it through the registry inside Ajustes, not its own mount", () => {
    // The extraction is what keeps this file inside its size budget, so a mount
    // added back here would undo it silently.
    const menu = source(PROFILE_MENU);
    expect(menu).toContain("<ProfileSettingsPanels");
    expect(menu).toContain("receipts: receiptsAvailable,");
    expect(menu).not.toContain("SharedReceiptsView");
    expect(menu).not.toContain("backToDataControls");
  });
});
