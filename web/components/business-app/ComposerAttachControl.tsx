"use client";

import { Plus, ReceiptText, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import ActionMenu from "./ActionMenu";
import { useBusiness } from "./BusinessWorkspace";

/**
 * The Business composer's leading control. It replaces the asset mention
 * picker. A receipt added here is saved to the Inbox; the chip says so until
 * the next send or conversation, and is never part of the message.
 */
export default function ComposerAttachControl() {
  const { t } = useTranslation();
  const { actions, attachedReceipt, clearAttachedReceipt, openPanel } = useBusiness();
  const label = t("business.composer.add", "Add");

  return (
    <div className="relative">
      {attachedReceipt ? (
        <div
          data-testid="composer-attached-receipt"
          className="absolute bottom-full left-0 mb-3 flex max-w-[min(20rem,80vw)] items-center gap-2 rounded-full border border-black/10 bg-white py-1 pl-3 pr-1 text-[13px] text-black/75 dark:border-white/10 dark:bg-[#1f2225] dark:text-white/75"
        >
          <ReceiptText className="h-4 w-4 shrink-0" />
          <button
            type="button"
            title={attachedReceipt.filename ?? undefined}
            className="min-w-0 truncate text-left font-medium hover:underline"
            onClick={() => openPanel({ kind: "receipt", receiptId: attachedReceipt.id })}
          >
            {t("business.composer_receipt.saved", "Saved to Inbox")}
          </button>
          <button
            type="button"
            aria-label={t("business.composer_receipt.dismiss", "Dismiss")}
            title={t("business.composer_receipt.dismiss", "Dismiss")}
            onClick={clearAttachedReceipt}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : null}
      <ActionMenu
        actions={actions.composer}
        label={label}
        placement="above-start-compact"
        renderTrigger={({ ref, open, toggle, menuId }) => (
          <button
            ref={ref}
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={toggle}
            aria-label={label}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-controls={open ? menuId : undefined}
            data-testid="business-composer-add"
            className="flex h-8 w-8 items-center justify-center rounded-full text-black/55 transition-colors hover:bg-black/5 hover:text-black focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/55 dark:hover:bg-white/5 dark:hover:text-white"
          >
            <Plus className="h-[18px] w-[18px]" />
          </button>
        )}
      />
    </div>
  );
}
