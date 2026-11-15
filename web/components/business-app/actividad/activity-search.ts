import { History } from "lucide-react";
import type { TFunction } from "i18next";
import type { WorkspaceSearchGroup, WorkspaceSearchHit, WorkspaceSearchPage } from "@/components/chat/ChatWorkspace";
import type { BusinessActivityItem, BusinessActivityPage } from "@/lib/business-activity-api";
import { formatDay } from "../business-format";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { activityActorName, activityPhrase, activityTarget } from "./activity-words";

export const ACTIVITY_GROUP = "activity";

type Context = Readonly<{ t: TFunction; locale: string; openPanel: (panel: BusinessPanelState) => void }>;

/**
 * Actividad's rows in the search window, as the server matched them: who and what, then the named record and the
 * day. A row opens what its Actividad row opens. `more` reads the next rows by the cursor the last answer gave.
 */
export function activitySearchGroup({ t, locale, openPanel }: Context, found: BusinessActivityPage | null, more: (cursor: string) => Promise<BusinessActivityPage>): WorkspaceSearchGroup {
  const label = t("business.nav.activity");
  if (!found) return { id: ACTIVITY_GROUP, label, hits: [], error: t("business.activity_feed.error_title") };
  const hit = (item: BusinessActivityItem): WorkspaceSearchHit => {
    const phrase = activityPhrase(t, item);
    const record = item.object?.purged ? undefined : item.object?.label;
    const target = activityTarget(item);
    return {
      id: item.id,
      icon: History,
      title: `${activityActorName(t, item.actor)} ${phrase}`,
      detail: [record && !phrase.includes(record) ? record : null, formatDay(item.occurred_at, locale)].filter(Boolean).join(" · "),
      amount: null,
      badge: label,
      ...(target ? { open: () => openPanel(target) } : {}),
    };
  };
  const pager = (cursor: string | null): (() => Promise<WorkspaceSearchPage>) | undefined =>
    cursor ? async () => { const page = await more(cursor); return { hits: page.items.map(hit), loadMore: pager(page.next_cursor) }; } : undefined;
  const loadMore = pager(found.next_cursor);
  return { id: ACTIVITY_GROUP, label, hits: found.items.map(hit), ...(loadMore ? { loadMore } : {}) };
}
