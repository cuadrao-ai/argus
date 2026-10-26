"use client";

import { ChevronDown, Copy, Download, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import ActionMenu from "./ActionMenu";
import { useBusiness } from "./BusinessWorkspace";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { useForwardAddress } from "./useForwardAddress";
import { copyText } from "./foundation/CopyButton";
import { showToast } from "./foundation/toasts";

/**
 * The one global action: Agregar, with a menu for the rarer ones (Exportar
 * registros, Copiar dirección de reenvío). It sits beside the content heading
 * from the tablet stop up and at the top of each screen on a phone.
 * A contador, who adds nothing, gets the menu alone.
 */
export default function BusinessAddMenu({ placement }: { placement: "header" | "page" }) {
  const { t } = useTranslation();
  const { actions, chosen, openExport, openPanel } = useBusiness();
  const forwardAddress = useForwardAddress();
  const owner = chosen?.role !== "accountant";
  const add = owner ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  const copyForward = async (address: string) => {
    const copied = await copyText(address);
    if (copied) showToast({ kind: "info", text: t("business.email.copied", "Address copied.") });
    else openPanel({ kind: "business", tab: "correo" });
  };
  const more = [
    ...(chosen?.capabilities.includes("read") ? [{ id: "export", icon: Download, label: t("business.overview.export_records", "Export records"), run: openExport }] : []),
    ...(owner && forwardAddress ? [{ id: "copy_forward", icon: Copy, label: t("business.overview.copy_forward", "Copy forwarding address"), run: () => void copyForward(forwardAddress) }] : []),
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
          data-add-primary
          aria-label={add.label}
          onClick={add.run}
          className={`${primaryButtonClass} rounded-r-none pl-4 pr-3 ${page ? "flex-1" : ""}`}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span data-add-label>{add.label}</span>
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
              ? `${primaryButtonClass} min-w-11 rounded-l-none border-l border-[var(--cuadrao-cream)]/25 px-3`
              : `${secondaryButtonClass} ${page ? "w-full" : ""}`}
          >
            {add ? null : moreLabel}
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      />
    </div>
  );
}
