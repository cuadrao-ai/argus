import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

describe("logout on the first click", () => {
  test("logout tells the account boundary before signing out, so one click leaves without the account-changed screen", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const logoutHandler = chat.slice(
      chat.indexOf("const handleLogout = async ("),
      chat.indexOf("const handleCancelConfirmationAction"),
    );
    // The provider's SIGNED_OUT event fires during logoutFromApi; a boundary
    // told first ignores it instead of rendering "account changed" + Reload.
    expect(logoutHandler.indexOf("accountBoundary.beginConversion()")).toBeLessThan(
      logoutHandler.indexOf("await logoutFromApi()"),
    );
    // A failed revocation hands the surface back to the signed-in account.
    expect(logoutHandler).toContain("accountBoundary.finishConversion(account?.user.id ?? null)");
    // Signed out, the Business page is the landing: it sends the browser to
    // login with return_to=/biz, never to the guest chat.
    expect(logoutHandler).toContain('window.location.href = "/biz"');
    expect(logoutHandler).not.toContain('window.location.href = "/"');
  });
});
