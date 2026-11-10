import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

// What a person may do in a Business is the server's permissions and capabilities for that Business
// (src/argus/domain/business/roles.py). The `role` label is legacy: every non-owner is "accountant", so an admin
// who prepares and a viewer who only reads look alike. Deciding an action from it hid Agregar from admins. The
// per-Business `business_role` is no better a gate: its permissions are the server's to derive.
const WEB = path.resolve(import.meta.dir, "..");
const ROLE_CHECK = /(?:\b|_)role\s*[!=]==?\s*["'](owner|accountant|admin|editor|viewer)["']|["'](owner|accountant|admin|editor|viewer)["']\s*[!=]==?\s*[\w?.]*(?:\b|_)role\b/;

/**
 * Role comparisons that name who someone is, never what they may do, keyed by file and a piece of the line.
 * A permission decision reads `capabilities` (canAddRecords) or `permissions` (canManageBusiness) instead.
 */
const ALLOWED: Record<string, Record<string, string>> = {
  "app/design-workspace/BusinessAccessPreview.tsx": {
    'person.role==="owner"&&!chosen.permissions.includes("assign_owner")': "the listed person's own role; changing an owner is gated on the server's assign_owner",
  },
  "app/design-workspace/businessAccessPreviewState.ts": {
    'role === "owner"&&!canAssignOwner': "an option in the role picker, gated on the server's assign_owner",
  },
  "app/design-workspace/ReceiptReadingPreview.tsx": {
    'canChange=chosen?.role === "owner"': "local preview only; the live control reads the server's can_change, which is the owner's alone",
  },
  "app/design-workspace/WorkspaceSetupPreview.tsx": {
    'shared: chosen.role !== "owner"': "whether the Business is someone else's, for the preview's wording",
  },
  "components/business-app/BusinessApp.tsx": {
    'closed.some(space => space.role === "owner")': "a closed Business the person owns, which only its owner may reopen",
  },
  "components/business-app/BusinessLifecycleControls.tsx": {
    'business.role === "owner" && !dismissed': "the closed Businesses the person owns, which only its owner may reopen",
  },
  "components/business-app/BusinessSettingsPanel.tsx": {
    'const owner = chosen?.role === "owner"': "closing the Business is its owner's alone; the server checks ownership, not a permission",
  },
  "components/business-app/BusinessSwitcher.tsx": {
    'closedSpaces.filter(space => space.role === "owner")': "the closed Businesses the person owns",
  },
  "components/business-app/BusinessTransferEntry.tsx": {
    'transfer.role === "owner"': "which side of an ownership transfer the person is on",
  },
  "components/business-app/BusinessWorkspace.tsx": {
    'chosenGrant ? space.grant_id === chosenGrant : space.role === "owner"': "with no grant chosen, the person's own Business",
    'listed.find(space => space.role === "owner")?.grant_id': "the person's own Business opens first",
    'if (!chosen || chosen.role === "owner") return;': "the owner holds no grant whose access notice to mark seen",
    'spaces.find(space => space.role === "owner") ? null': "return to the person's own Business",
  },
  "components/business-app/ExportRecordsPanel.tsx": {
    'chosen.role === "owner" && getChosenGrant() === null': "the own Business is addressed without a grant header",
  },
  "components/business-app/ReceiptMarksCard.tsx": {
    'const owner = !chosen || chosen.role === "owner"': "the owner reads who answered; the answer itself is gated on the dossier's capabilities",
  },
  "components/business-app/business-ui.tsx": {
    'business.chosen.role === "owner"': "useOwnerView: the owner is looking at their own Business, for attribution only",
  },
  "components/business-app/useAccessBanner.ts": {
    'chosen.role !== "owner" && !chosen.access_seen': "the one-time notice for access to someone else's Business",
  },
  "lib/business-grant.ts": {
    'spaces[0].role === "owner"': "a lone grant on someone else's Business opens by default",
  },
};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "node_modules" ? [] : sources(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

const checks = ["app", "components", "lib"].flatMap((dir) => sources(path.join(WEB, dir))).flatMap((file) => {
  const relative = path.relative(WEB, file);
  return readFileSync(file, "utf8").split("\n").flatMap((line, index) => (ROLE_CHECK.test(line) ? [{ file: relative, line: index + 1, text: line.trim() }] : []));
});

describe("permissions come from the server, not the role label", () => {
  test("no web code compares the role label outside the owner-identity allow-list", () => {
    const offenders = checks
      .filter((check) => !Object.keys(ALLOWED[check.file] ?? {}).some((piece) => check.text.includes(piece)))
      .map((check) => `${check.file}:${check.line}: ${check.text.slice(0, 160)}`);
    expect(offenders).toEqual([]);
  });

  test("each allowed comparison still exists and says why it is identity, not permission", () => {
    for (const [file, pieces] of Object.entries(ALLOWED)) {
      for (const [piece, reason] of Object.entries(pieces)) {
        expect(reason.length).toBeGreaterThan(20);
        expect(checks.some((check) => check.file === file && check.text.includes(piece))).toBe(true);
      }
    }
  });

  test("the guard catches the shape that hid Agregar from admins", () => {
    expect(ROLE_CHECK.test('const owner = chosen?.role !== "accountant";')).toBe(true);
    expect(ROLE_CHECK.test('if ("owner" === space.role) {')).toBe(true);
    expect(ROLE_CHECK.test('chosen.business_role === "admin"')).toBe(true);
    expect(ROLE_CHECK.test('"viewer" !== grant.business_role')).toBe(true);
    expect(ROLE_CHECK.test('message.role === "user"')).toBe(false);
  });
});
