"use client";

import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { formatTimestamp } from "../business-format";
import { useChannelLabel } from "../business-ui";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { DossierNoteCard, DossierSupportingCard, dossierFileSize, type DossierAnnotationsProps } from "./DossierAnnotations";
import { DossierCard, DossierRows } from "./DossierParts";
import styles from "./dossier.module.css";

/** Where a record came from and what its file is, as the server names each. A fact the server did not send reads "Sin dato". */
export type DossierOrigin = { channel?: keyof typeof CHANNEL_ICON | null; sentBy?: string | null; receivedAt?: string | null; filename?: string | null; sizeBytes?: number | null };

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

/** Detalles holds origin, record annotations and the original file's metadata. */
export default function DossierDetails({ origin, ...annotations }: { origin: DossierOrigin } & DossierAnnotationsProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const channelLabel = useChannelLabel();
  const Icon = origin.channel ? CHANNEL_ICON[origin.channel] : null;
  const { busy, dossier, detailsCard, entryVisit, onSaveNote, onNoteDirty, ...supporting } = annotations;
  return (
    <div className={styles.stack} data-testid="dossier-details">
      <DossierCard title={t("business.dossier.details.origin")}>
        <DossierRows>
          <Row fact="channel" label={t("business.dossier.details.channel")} value={origin.channel ? channelLabel(origin.channel) : null} icon={Icon ? <Icon size={16} aria-hidden="true" /> : null} />
          <Row fact="sent_by" label={t("business.dossier.details.sent_by")} value={origin.sentBy} />
          <Row fact="received_at" label={t("business.dossier.details.arrived")} value={origin.receivedAt ? formatTimestamp(origin.receivedAt, locale) : null} />
        </DossierRows>
      </DossierCard>
      {dossier ? <DossierNoteCard key={`note-${dossier.draft_id}`} busy={busy} dossier={dossier} detailsCard={detailsCard} entryVisit={entryVisit} onSaveNote={onSaveNote} onNoteDirty={onNoteDirty} /> : null}
      {dossier || detailsCard === "support" ? <DossierSupportingCard key={`support-${dossier?.draft_id ?? "receipt"}`} busy={busy} dossier={dossier} detailsCard={detailsCard} entryVisit={entryVisit} {...supporting} /> : null}
      <DossierCard title={t("business.dossier.details.file")}>
        <DossierRows>
          <Row fact="filename" label={t("business.dossier.details.name")} value={origin.filename} />
          <Row fact="size" label={t("business.dossier.details.size")} value={origin.sizeBytes != null ? dossierFileSize(origin.sizeBytes, locale) : null} />
        </DossierRows>
      </DossierCard>
    </div>
  );
}
