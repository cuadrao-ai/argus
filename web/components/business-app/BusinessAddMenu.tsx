"use client";

import { ChevronDown, Copy, Download, Mail, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import ActionMenu from "./ActionMenu";
import { useBusiness } from "./BusinessWorkspace";
import { useForwardAddress } from "./useForwardAddress";
import { copyText } from "./foundation/CopyButton";
import { showToast } from "./foundation/toasts";

const focusRing = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]";

/**
 * The one global action: Agregar, with a menu for the rarer ones (Exportar
 * registros, Copiar dirección de reenvío, Ver correos). It sits in the top bar
 * from the tablet stop up and at the top of each screen on a phone, where the
 * thumb reaches it. A contador, who adds nothing, gets the menu alone.
 */
export default function BusinessAddMenu({ placement }: { placement: "header" | "page" }) {
  const { t } = useTranslation();
  const { actions, chosen, openExport, openPanel } = useBusiness();
  const forwardAddress = useForwardAddress();
  const owner = chosen?.role !== "accountant";
  const add = owner ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  const copyForward = async (address: string) => {
    const copied = await copyText(address);
    showToast(copied
      ? { kind: "info", text: t("business.email.copied", "Address copied.") }
      : { kind: "error", text: t("business.overview.copy_forward_failed", { address, defaultValue: "Could not copy. Your forwarding address is {{address}}" }) });
  };
  const more = [
    ...(chosen?.capabilities.includes("read") ? [{ id: "export", icon: Download, label: t("business.overview.export_records", "Export records"), run: openExport }] : []),
    ...(owner && forwardAddress ? [{ id: "copy_forward", icon: Copy, label: t("business.overview.copy_forward", "Copy forwarding address"), run: () => void copyForward(forwardAddress) }] : []),
    { id: "emails", icon: Mail, label: t("business.inbox.see_emails", "See emails"), run: () => openPanel({ kind: "inbox", segment: "emails" }) },
  ];
  const page = placement === "page";
  const moreLabel = t("business.add_menu.more", "More actions");
  return (
    <div data-testid={`add-menu-${placement}`} className={`flex items-stretch ${page ? "w-full" : ""}`}>
      {add ? (
        <button
          type="button"
          data-testid="business-primary-upload"
          data-primary="true"
          onClick={add.run}
          className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-l-full bg-[#2f5a49] pl-4 pr-3 text-[15px] font-medium text-[#FFFEFA] hover:bg-[#1d4236] ${page ? "flex-1" : ""} ${focusRing}`}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {add.label}
        </button>
      ) : null}
      <ActionMenu
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
              ? `inline-flex min-h-11 min-w-11 items-center justify-center rounded-r-full border-l border-[#FFFEFA]/25 bg-[#2f5a49] px-3 text-[#FFFEFA] hover:bg-[#1d4236] ${focusRing}`
              : `inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-[#7d8a84] bg-[#FFFEFA] px-4 text-[15px] font-medium text-[#172b26] dark:bg-[#1f2225] dark:text-white ${page ? "w-full" : ""} ${focusRing}`}
          >
            {add ? null : moreLabel}
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      />
    </div>
  );
}
