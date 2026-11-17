import type { TFunction } from "i18next";
import type { BusinessActivityActor } from "@/lib/business-activity-api";
import { personName } from "@/lib/person-name";
import type { BusinessPanelState } from "../BusinessWorkspace";

type Row = Readonly<{
  actor: BusinessActivityActor | null;
  action: string;
  object: { kind: string; id: string; label?: string; purged?: boolean } | null;
}>;

/** Who a row names: Cuadrao for automated work, the person as the server shows them, or that no one was recorded. */
export function activityActorName(t: TFunction, actor: Row["actor"]): string {
  if (!actor) return t("business.activity_feed.no_actor");
  if (actor.kind === "extractor") return t("business.activity_feed.extractor_name");
  return personName(t, actor);
}

/** What a row did, in words. A purged document is "un documento": it has no name. An action with no words yet reads as a change. */
export function activityPhrase(t: TFunction, item: Pick<Row, "action" | "object">): string {
  const document = item.object?.purged ? t("business.document_delete.purged_document") : item.object?.label ?? t("business.document_delete.unnamed");
  return t([`business.activity_feed.actions.${item.action}`, "business.activity_feed.actions.other"], { document });
}

/**
 * Where a row leads, for the Actividad screen and the search window alike: the receipt or the record the server
 * names. A deleted document leads to Eliminados, and a restored one opens beside the Bandeja it returned to. A purged
 * document, an access change and a row that names nothing lead nowhere.
 */
export function activityTarget(item: Pick<Row, "action" | "object">): BusinessPanelState | null {
  const object = item.object;
  if (object?.purged) return null;
  if (item.action === "delete_document") return { kind: "inbox", view: "eliminados" };
  const list = item.action === "restore_document" ? { list: "inbox" as const } : {};
  if (object?.kind === "receipt") return { kind: "receipt", receiptId: object.id, ...list };
  if (object?.kind === "draft") return { kind: "draft", draftId: object.id, ...list };
  return null;
}
