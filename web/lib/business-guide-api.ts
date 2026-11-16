import { z } from "zod";
import { apiFetch } from "./argus-api-transport";

/** The server owns the card IDs; a test pins this list to the `card_id` enum in docs/api/openapi.yaml. */
export const BUSINESS_GUIDE_CARD_IDS = ["actividad-intro", "bandeja-intro", "exportar-guardar", "registros-intro"] as const;
export type BusinessGuideCardId = (typeof BUSINESS_GUIDE_CARD_IDS)[number];

type DismissRequest = {
  cardId: BusinessGuideCardId;
  expectedUserId: string;
};

const dismissedGuideState = z.object({ dismissed: z.literal(true) });

/** Whether a guide was dismissed arrives with `GET /me`; this only saves a dismissal. */
export async function dismissBusinessGuideCard({ cardId, expectedUserId }: DismissRequest) {
  return dismissedGuideState.parse(await apiFetch<unknown>(`/business/guide-cards/${cardId}/dismiss`, { expectedUserId, method: "POST" }));
}
