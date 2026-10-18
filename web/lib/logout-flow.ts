/**
 * Leaving a signed-in session in one click. The account boundary is told
 * first, so the provider's SIGNED_OUT event that fires during sign-out is
 * expected and never swaps the surface for the account-changed screen. A
 * failed revocation still clears the local session, lands on the signed-out
 * screen, and says so once. It does not send the request again. Signed out,
 * a Business build opens the login page directly. Any other build opens the
 * landing page. A session that ended because the account was deleted goes to
 * the landing page on every build: someone who just deleted their account
 * must not land on a Business login. While this sign-out is in progress, a
 * null session is ours and must not paint the account-changed alert.
 */
let leavingSession = false;
let inFlight: Promise<"left" | "failed"> | null = null;

export function isLeavingSession(): boolean {
  return leavingSession;
}
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
  return businessBuild && !accountDeleted ? "/?auth=login" : "/";
}

async function leaveSessionOnce(deps: LeaveSessionDeps): Promise<"left" | "failed"> {
  leavingSession = true;
  deps.boundary.beginConversion();
  let failed = false;
  try {
    const result = await deps.signOut();
    failed = result?.revocation === "failed" || result?.cookieSync === "failed";
  } catch {
    failed = true;
  }
  if (failed) deps.onFailed();
  deps.clearLocalState();
  deps.navigate(signedOutLanding(deps.businessBuild, deps.accountDeleted));
  return failed ? "failed" : "left";
}

export function leaveSession(deps: LeaveSessionDeps): Promise<"left" | "failed"> {
  if (inFlight) return inFlight;
  const flight = leaveSessionOnce(deps).finally(() => {
    if (inFlight === flight) inFlight = null;
  });
  inFlight = flight;
  return flight;
}
