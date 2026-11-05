"use client";

import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { KeyboardDeleteRequest } from "@/lib/keyboard-shortcuts";

type ConversationDeleteDialogProps = {
  pending: KeyboardDeleteRequest | null;
  title: string;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function ConversationDeleteDialog({
  pending,
  title,
  isDeleting,
  onCancel,
  onConfirm,
}: ConversationDeleteDialogProps) {
  const { t } = useTranslation();
  return (
    <ConfirmDialog
      isOpen={Boolean(pending)}
      title={t("sidebar.delete_confirm.title", "Delete this conversation?")}
      description={t(
        "sidebar.delete_confirm.description",
        "This moves “{{title}}” to Recently Deleted. You can restore it before permanent removal.",
        { title },
      )}
      confirmLabel={t("sidebar.delete_confirm.confirm", "Delete conversation")}
      cancelLabel={t("common.cancel", "Cancel")}
      isBusy={isDeleting}
      showKeyboardHints={pending?.showKeyboardHints}
      onCancel={() => {
        if (!isDeleting) onCancel();
      }}
      onConfirm={onConfirm}
    />
  );
}
