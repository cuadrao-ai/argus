"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  MessageSquareText,
  Plus,
  ReceiptText,
  type LucideIcon,
} from "lucide-react";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import type { WorkspaceStarterEntry } from "@/components/chat/StarterActions";
import {
  businessChatAvailable,
  type BusinessOverview,
  type BusinessWorkspaceInfo,
  type ReceiptActivityCounts,
  type ReceiptSummary,
} from "@/lib/business-api";
import type { BusinessPanelState } from "./BusinessWorkspace";
import { useBusinessConsent } from "./business-consent-context";
import type { IntakeTarget } from "./ReceiptIntakeDialog";

export type BusinessActionId =
  | "upload_receipt"
  | "ask_spending";

export type BusinessAction = Readonly<{
  id: BusinessActionId;
  label: string;
  icon: LucideIcon;
  run: () => void;
}>;

export type BusinessActions = Readonly<{
  /**
   * The + Create menu: records you can start from anywhere. New chat keeps its
   * one entry point at the top of the sidebar, as Slack keeps compose apart
   * from its + menu.
   */
  create: readonly BusinessAction[];
  /** The composer's + control: actions that attach to this conversation. */
  composer: readonly BusinessAction[];
  starterEntries: readonly WorkspaceStarterEntry[];
}>;

type ActionInput = {
  records: {
    workspace: BusinessWorkspaceInfo | null;
    overview: BusinessOverview | null;
    inbox: ReceiptSummary[] | null;
    receiptActivity?: ReceiptActivityCounts | null;
    error?: boolean;
  };
  bridge: ChatShellBridge | null;
  openIntake: (target: IntakeTarget) => void;
  openPanel: (panel: BusinessPanelState) => void;
};

/**
 * The one owner of what Create, the composer and the starter chips can do.
 * Opening any of them never uploads, calls AI or confirms an expense.
 */
export function useBusinessActions({
  records,
  bridge,
  openIntake,
}: ActionInput): BusinessActions {
  const { t } = useTranslation();
  const consent = useBusinessConsent();
  const canAsk =
    consent.accepted &&
    businessChatAvailable(records.workspace) &&
    Boolean(records.workspace?.assistant_available) &&
    (records.overview?.totals ?? []).some((total) => total.count > 0);

  return useMemo(() => {
    const action = (
      id: BusinessActionId,
      label: string,
      icon: LucideIcon,
      run: () => void,
    ): BusinessAction => ({ id, label, icon, run });

    // One door for everything the business records: a file, a photo or typed text all become a Bandeja draft.
    const add = action(
      "upload_receipt",
      t("business.actions.add", "Add"),
      Plus,
      () => openIntake("inbox"),
    );
    const askSpending = action(
      "ask_spending",
      t("business.actions.ask_spending", "What did I spend this month?"),
      MessageSquareText,
      () =>
        bridge?.prepareQuestion(
          t("business.actions.ask_spending", "What did I spend this month?"),
        ),
    );
    const attachReceipt = action(
      "upload_receipt",
      t("business.actions.attach_receipt", "Add a receipt"),
      ReceiptText,
      () => openIntake("composer"),
    );

    const chips = [add, ...(canAsk ? [askSpending] : [])];
    return {
      create: [add],
      composer: [attachReceipt],
      starterEntries: chips.map(({ id, icon, label, run }) => ({ key: id, icon, label, onSelect: run })),
    };
  }, [bridge, canAsk, openIntake, t]);
}
