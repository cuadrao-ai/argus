"use client";

import { ChevronDown, Copy, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import ActionMenu from "./ActionMenu";
import { useBusiness } from "./BusinessWorkspace";
import { canAddRecords, primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { useForwardAddress } from "./useForwardAddress";
import { copyText } from "./foundation/CopyButton";
import { showToast } from "./foundation/toasts";

export default function BusinessAddMenu({ placement }: { placement: "header" | "page" }) {
  const { t } = useTranslation();
  const { actions, chosen, openPanel } = useBusiness();
  const forwardAddress = useForwardAddress();
  const canAdd = canAddRecords(chosen);
  const add = canAdd ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  const copyForward = async (address: string) => {
    const copied = await copyText(address);
    if (copied) showToast({ kind: "info", text: t("business.email.copied", "Address copied.") });
    else openPanel({ kind: "business", tab: "correo" });
  };
  const more = [
    ...(canAdd && forwardAddress ? [{ id: "copy_forward", icon: Copy, label: t("business.overview.copy_forward", "Copy forwarding address"), run: () => void copyForward(forwardAddress) }] : []),
  ];
  const hasMore = more.length > 0;
  if (!add && !hasMore) return null;
  const page = placement === "page";
  const moreLabel = t("business.add_menu.more", "More actions");
  return (
    <div data-testid={`add-menu-${placement}`} className={`flex items-stretch ${page ? "w-fit ml-auto" : ""}`}>
      {add ? (
        <button
          type="button"
          data-testid="business-primary-upload"
          data-primary="true"
          data-add-primary
          aria-label={add.label}
          onClick={add.run}
          className={`${primaryButtonClass} ${hasMore ? "rounded-r-none" : ""} pl-4 pr-3`}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span data-add-label>{add.label}</span>
        </button>
      ) : null}
      {hasMore ? <ActionMenu
        actions={more}
        label={moreLabel}
        placement="below-end"
        portal
        renderTrigger={({ ref, open, toggle, menuId }) => (
          <button
            ref={ref}
            type="button"
            data-testid="add-menu-more"
            aria-label={moreLabel}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-controls={open ? menuId : undefined}
            onClick={toggle}
            className={add
              ? `${primaryButtonClass} min-w-11 rounded-l-none border-l border-[var(--cuadrao-cream)]/25 px-3`
              : `${secondaryButtonClass} ${page ? "w-full" : ""}`}
          >
            {add ? null : moreLabel}
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      /> : null}
    </div>
  );
}
