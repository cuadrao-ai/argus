"use client";

import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { formatTimestamp } from "../business-format";
import { useChannelLabel } from "../business-ui";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { DossierCard, DossierRows } from "./DossierParts";
import styles from "./dossier.module.css";

/** Where a record came from and what its file is, as the server names each. A fact the server did not send reads "Sin dato". */
export type DossierOrigin = { channel?: keyof typeof CHANNEL_ICON | null; sentBy?: string | null; receivedAt?: string | null; filename?: string | null; sizeBytes?: number | null };

function fileSize(bytes: number, locale: string): string {
  const [amount, unit] = bytes >= 1_048_576 ? [bytes / 1_048_576, "megabyte"] : bytes >= 1024 ? [bytes / 1024, "kilobyte"] : [bytes, "byte"];
  return new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "short", maximumFractionDigits: unit === "megabyte" ? 1 : 0 }).format(amount);
}

function Row({ fact, label, value, icon }: { fact: string; label: string; value: string | null | undefined; icon?: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <li className={styles.row} data-fact={fact}>
      <span className={styles.label}>{label}</span>
      <span className={styles.slot}>{icon ? <span className={styles.icon}>{icon}</span> : null}</span>
      <span className={styles.value} data-empty={value ? undefined : true}>{value || t("business.dossier.row.no_data")}</span>
      <span className={styles.actions} />
    </li>
  );
}

/** The Detalles tab: Origen (Canal, Enviado por, Llegada) and Archivo (Nombre, Tamaño). Nothing here can be edited. */
export default function DossierDetails({ origin }: { origin: DossierOrigin }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const channelLabel = useChannelLabel();
  const Icon = origin.channel ? CHANNEL_ICON[origin.channel] : null;
  return (
    <div className={styles.stack} data-testid="dossier-details">
      <DossierCard title={t("business.dossier.details.origin")}>
        <DossierRows>
          <Row fact="channel" label={t("business.dossier.details.channel")} value={origin.channel ? channelLabel(origin.channel) : null} icon={Icon ? <Icon size={16} aria-hidden="true" /> : null} />
          <Row fact="sent_by" label={t("business.dossier.details.sent_by")} value={origin.sentBy} />
          <Row fact="received_at" label={t("business.dossier.details.arrived")} value={origin.receivedAt ? formatTimestamp(origin.receivedAt, locale) : null} />
        </DossierRows>
      </DossierCard>
      <DossierCard title={t("business.dossier.details.file")}>
        <DossierRows>
          <Row fact="filename" label={t("business.dossier.details.name")} value={origin.filename} />
          <Row fact="size" label={t("business.dossier.details.size")} value={origin.sizeBytes != null ? fileSize(origin.sizeBytes, locale) : null} />
        </DossierRows>
      </DossierCard>
    </div>
  );
}
