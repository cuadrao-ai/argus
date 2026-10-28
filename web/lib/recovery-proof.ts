// The one shape of "this browser's session came from a verified recovery
// link": the user id and a fingerprint of the session id, computed by whichever
// hop verified the link (the browser PKCE exchange or the server confirm route)
// and checked by the recovery page against its live session.

export const RECOVERY_PROOF_PARAM = "recovery_proof";

const PROOF = /^[A-Za-z0-9-]{1,64}:[0-9a-f]{64}$/;

export async function recoveryProof(userId: string, sessionId: string): Promise<string> {
  const bytes = new TextEncoder().encode(sessionId);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const fingerprint = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${userId}:${fingerprint}`;
}

export function sessionIdFromAccessToken(accessToken: string): string | null {
  const payload = accessToken.split(".")[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(payload.length / 4) * 4, "="));
    const claims = JSON.parse(json) as { session_id?: unknown };
    return typeof claims.session_id === "string" && claims.session_id ? claims.session_id : null;
  } catch {
    return null;
  }
}

/** The recovery page location that hands the proof over in the fragment, which never reaches a server or its logs. */
export function recoveryProofLocation(next: string, proof: string): string {
  const hashAt = next.indexOf("#");
  const base = hashAt === -1 ? next : next.slice(0, hashAt);
  return `${base}#${RECOVERY_PROOF_PARAM}=${proof}`;
}

export function recoveryProofFromHash(hash: string): string | null {
  const value = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash).get(RECOVERY_PROOF_PARAM);
  return value && PROOF.test(value) ? value : null;
}
