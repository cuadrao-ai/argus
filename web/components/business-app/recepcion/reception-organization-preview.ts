/** Local interaction state only. These actions never mutate source documents. */
export type OrganizationAction = "archive" | "restore" | "seen" | "unseen";
export type OrganizationPreview = { archived: string[]; unseen: string[] };
export const emptyOrganizationPreview = (): OrganizationPreview => ({ archived: [], unseen: [] });

export function applyOrganizationPreview(state: OrganizationPreview, ids: readonly string[], action: OrganizationAction): OrganizationPreview {
  const field = action === "archive" || action === "restore" ? "archived" : "unseen";
  const add = action === "archive" || action === "unseen";
  const changed = add ? [...new Set([...state[field], ...ids])] : state[field].filter(id => !ids.includes(id));
  return { ...state, [field]: changed };
}

/** Restore prior membership for this action only; preserve unrelated arrivals and facts. */
export function undoOrganizationPreview(state: OrganizationPreview, before: OrganizationPreview, ids: readonly string[], action: OrganizationAction): OrganizationPreview {
  const field = action === "archive" || action === "restore" ? "archived" : "unseen";
  const retained = state[field].filter(id => !ids.includes(id));
  return { ...state, [field]: [...retained, ...before[field].filter(id => ids.includes(id))] };
}
