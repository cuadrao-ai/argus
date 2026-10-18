/**
 * Leaving a signed-in session in one click. The account boundary is told
 * first, so the provider's SIGNED_OUT event that fires during sign-out is
 * expected and never swaps the surface for the account-changed screen. A
 * failed revocation hands the surface back and says so; nothing is cleared
 * and nothing navigates. Signed out, the browser goes to the Business page
 * on a Business build (it sends a signed-out visitor to login with
 * return_to=/biz) and to the landing page otherwise. A session that ended
 * because the account was deleted goes to the landing page on every build:
 * someone who just deleted their account must not land on a Business login.
 */
export type LeaveSessionDeps = {
  boundary: { beginConversion: () => void; finishConversion: (userId: string | null) => void };
  currentUserId: string | null;
  /** Resolves null when the session already ended elsewhere and no sign-out is owed. */
  signOut: () => Promise<{ revocation: "complete" | "failed"; cookieSync?: "cleared" | "failed" } | null>;
  clearLocalState: () => void;
  navigate: (href: string) => void;
  onFailed: () => void;
  businessBuild: boolean;
  /** The account was deleted and the session already ended: nothing to sign out of, and no Business login to land on. */
  accountDeleted?: boolean;
};

export function signedOutLanding(businessBuild: boolean, accountDeleted = false): string {
  return businessBuild && !accountDeleted ? "/biz" : "/";
}

export async function leaveSession(deps: LeaveSessionDeps): Promise<"left" | "failed"> {
  deps.boundary.beginConversion();
  try {
    const result = await deps.signOut();
    if (result?.revocation === "failed" || result?.cookieSync === "failed") {
      deps.boundary.finishConversion(deps.currentUserId);
      deps.onFailed();
      return "failed";
    }
  } catch {
    deps.boundary.finishConversion(deps.currentUserId);
    deps.onFailed();
    return "failed";
  }
  deps.clearLocalState();
  deps.navigate(signedOutLanding(deps.businessBuild, deps.accountDeleted));
  return "left";
}
