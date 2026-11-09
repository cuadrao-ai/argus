import { z } from "zod";
import { apiFetch } from "./argus-api-transport";

export type BusinessGuideCardId = "bandeja-intro";

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

