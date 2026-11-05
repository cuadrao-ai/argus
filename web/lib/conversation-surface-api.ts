import { apiFetch } from "./argus-api-transport";
import type { DecisionState, HistoryItem, SearchResponse } from "./argus-api";

/**
 * Which of a person's chat histories a request reads or writes. The client
 * names a surface and never a space; the server resolves Business to the
 * person's own space. Personal sends no parameter, so every /chat request
 * stays exactly what it was before Business existed.
 */
export type ConversationSurface = "personal" | "business";

export function appendSurface(params: URLSearchParams, surface: ConversationSurface | undefined) {
  if (surface === "business") params.append("surface", surface);
  return params;
}

export function surfaceQuery(surface: ConversationSurface | undefined) {
  return surface === "business" ? "?surface=business" : "";
}

export async function listHistory(
  params: {
    limit?: number;
    cursor?: string;
    archived?: boolean;
    deleted?: boolean;
    surface?: ConversationSurface;
  } = {},
) {
  const { limit = 20, cursor, archived, deleted, surface } = params;
  const searchParams = new URLSearchParams({ limit: String(limit) });
  if (cursor) searchParams.append("cursor", cursor);
  if (archived !== undefined) searchParams.append("archived", String(archived));
  if (deleted !== undefined) searchParams.append("deleted", String(deleted));
  appendSurface(searchParams, surface);

  return apiFetch<{ items: HistoryItem[]; next_cursor: string | null }>(
    `/history?${searchParams.toString()}`,
  );
}

export async function searchGlobal(params: {
  q: string;
  limit?: number;
  cursor?: string;
  decisionState?: DecisionState | null;
  includeLedgerGroups?: boolean;
  conversationIds?: string[];
  surface?: ConversationSurface;
}) {
  const {
    q,
    limit = 20,
    cursor,
    decisionState,
    includeLedgerGroups = false,
    conversationIds,
    surface,
  } = params;
  const searchParams = new URLSearchParams({
    q,
    limit: String(limit),
  });
  if (cursor) searchParams.append("cursor", cursor);
  if (decisionState) searchParams.append("decision_state", decisionState);
  if (includeLedgerGroups) {
    searchParams.append("include_ledger_groups", "true");
  }
  for (const id of conversationIds ?? [])
    searchParams.append("conversation_id", id);
  appendSurface(searchParams, surface);
  return apiFetch<SearchResponse>(
    `/search?${searchParams.toString()}`,
  );
}
