import type { TFunction } from "i18next";
import type { BusinessPanelState } from "../BusinessWorkspace";

type Row = Readonly<{
  actor: { display_name: string; kind: string } | null;
  action: string;
  object: { kind: string; id: string; label?: string; purged?: boolean } | null;
}>;

/** Who a row names: Cuadrao for automated work, the erased account's stand-in, or that no one was recorded. */
export function activityActorName(t: TFunction, actor: Row["actor"]): string {
  if (!actor) return t("business.activity_feed.no_actor");
  if (actor.kind === "extractor") return t("business.activity_feed.extractor_name");
  // An erased account reaches us already renamed.
  return actor.display_name === "Exmiembro" ? t("business.activity_feed.former_member") : actor.display_name;
}

/** What a row did, in words. A purged document is "un documento": it has no name. An action with no words yet reads as a change. */
export function activityPhrase(t: TFunction, item: Pick<Row, "action" | "object">): string {
  const document = item.object?.purged ? t("business.document_delete.purged_document") : item.object?.label ?? t("business.document_delete.unnamed");
  return t([`business.activity_feed.actions.${item.action}`, "business.activity_feed.actions.other"], { document });
}

/** Where a row leads: a deleted document to Eliminados, a restored one to itself. Nothing opens a purged document. */
export function activityTarget(item: Pick<Row, "action" | "object">): BusinessPanelState | null {
  if (item.object?.purged) return null;
  if (item.action === "delete_document") return { kind: "inbox", view: "eliminados" };
  if (item.action === "restore_document" && item.object?.kind === "receipt") return { kind: "receipt", receiptId: item.object.id, list: "inbox" };
  if (item.action === "restore_document" && item.object?.kind === "draft") return { kind: "draft", draftId: item.object.id, list: "inbox" };
  return null;
}
