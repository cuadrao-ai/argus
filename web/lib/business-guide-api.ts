import { z } from "zod";
import { apiFetch } from "./argus-api-transport";

/** The server owns the card IDs; a test pins this list to the `card_id` enum in docs/api/openapi.yaml. */
export const BUSINESS_GUIDE_CARD_IDS = ["actividad-intro", "bandeja-intro", "registros-intro"] as const;
export type BusinessGuideCardId = (typeof BUSINESS_GUIDE_CARD_IDS)[number];

type GuideRequest = {
  cardId: BusinessGuideCardId;
  expectedUserId: string;
  signal: AbortSignal;
};

const guideState = z.object({ dismissed: z.boolean() });
const dismissedGuideState = guideState.extend({ dismissed: z.literal(true) });

export async function getBusinessGuideCard({ cardId, expectedUserId, signal }: GuideRequest) {
  return guideState.parse(await apiFetch<unknown>(`/business/guide-cards/${cardId}`, { expectedUserId, signal, cache: "no-store" }));
}

export async function dismissBusinessGuideCard({ cardId, expectedUserId, signal }: GuideRequest) {
  return dismissedGuideState.parse(await apiFetch<unknown>(`/business/guide-cards/${cardId}/dismiss`, { expectedUserId, signal, method: "POST" }));
}

