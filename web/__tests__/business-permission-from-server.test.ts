import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

// What a person may do in a Business is the server's permissions and capabilities for that Business
// (src/argus/domain/business/roles.py). The `role` label is legacy: every non-owner is "accountant", so an admin
// who prepares and a viewer who only reads look alike. Deciding an action from it hid Agregar from admins. The
// per-Business `business_role` is no better a gate: its permissions are the server's to derive.
const WEB = path.resolve(import.meta.dir, "..");
const LABEL = "[\"'`](?:owner|accountant|admin|editor|viewer)[\"'`]";
/** Any name ending in role or Role: `role`, `chosen?.role`, `business_role`, `memberRole`. */
const ROLE = "[\\w?.]*[Rr]ole\\b";
/** A role compared with a label either way round, membership in a list of labels, and a switch over a role. */
const ROLE_CHECKS = [
  new RegExp(`${ROLE}\\s*[!=]==?\\s*${LABEL}`),
  new RegExp(`${LABEL}\\s*[!=]==?\\s*${ROLE}`),
  new RegExp(`\\.includes\\(\\s*${ROLE}`),
  new RegExp(`\\.has\\(\\s*${ROLE}`),
  new RegExp(`switch\\s*\\(\\s*${ROLE}`),
];
const isRoleCheck = (line: string) => ROLE_CHECKS.some((check) => check.test(line));

/**
 * Role comparisons that name who someone is, never what they may do, keyed by file and a piece of the line.
 * A permission decision reads `capabilities` (canAddRecords) or `permissions` (canManageBusiness) instead.
 */
const ALLOWED: Record<string, Record<string, string>> = {
  "app/design-workspace/BusinessAccessPreview.tsx": {
    'person.role==="owner"&&!chosen.permissions.includes("assign_owner")': "the listed person's own role; changing an owner is gated on the server's assign_owner",
    'memberEmail && memberRole === "owner" ?': "the local sketch, never live, seeds its preview owner from the person's own Business",
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
  return readFileSync(file, "utf8").split("\n").flatMap((line, index) => (isRoleCheck(line) ? [{ file: relative, line: index + 1, text: line.trim() }] : []));
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
    expect(isRoleCheck('const owner = chosen?.role !== "accountant";')).toBe(true);
    expect(isRoleCheck('if ("owner" === space.role) {')).toBe(true);
    expect(isRoleCheck('chosen.business_role === "admin"')).toBe(true);
    expect(isRoleCheck('"viewer" !== grant.business_role')).toBe(true);
    expect(isRoleCheck('message.role === "user"')).toBe(false);
  });

  test("the guard catches every other way to read a role label", () => {
    expect(isRoleCheck('if (memberRole === "owner") {')).toBe(true);
    expect(isRoleCheck('const admin = "admin" !== chosen.businessRole;')).toBe(true);
    expect(isRoleCheck("const owner = chosen.role === `owner`;")).toBe(true);
    expect(isRoleCheck('const prepares = ["owner", "admin"].includes(chosen.role);')).toBe(true);
    expect(isRoleCheck("const prepares = PREPARERS.includes(chosen?.business_role);")).toBe(true);
    expect(isRoleCheck('const prepares = new Set(["owner", "admin"]).has(chosen.role);')).toBe(true);
    expect(isRoleCheck("switch (chosen.role) {")).toBe(true);
    expect(isRoleCheck("switch (memberRole) {")).toBe(true);
    expect(isRoleCheck('const prepares = ["owner", "admin"].includes(chosen.role ?? "");')).toBe(true);
    expect(isRoleCheck('switch (chosen?.role ?? "none") {')).toBe(true);
    expect(isRoleCheck('const label = roleLabel === "owner";')).toBe(false);
    expect(isRoleCheck("const roles = people.map((person) => person.role);")).toBe(false);
  });
});
