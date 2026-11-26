"use client";

import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import type { BusinessDossier, RecordOrigin } from "@/lib/business-dossier";
import { sentByName } from "@/lib/sent-by";
import { resolveLanguage } from "@/lib/language-features";
import { formatTimestamp } from "../business-format";
import { useChannelLabel } from "../business-ui";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { DossierNoteCard, DossierSupportingCard, dossierFileSize, type DossierAnnotationsProps } from "./DossierAnnotations";
import { DossierCard, DossierRows } from "./DossierParts";
import styles from "./dossier.module.css";

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

type DetailsProps = Omit<DossierAnnotationsProps, "dossier"> & (
  | { dossier: BusinessDossier; receipt?: never }
  | { receipt: Pick<ReceiptSummary, keyof RecordOrigin>; dossier?: never }
);

export default function DossierDetails({ receipt, dossier, ...annotations }: DetailsProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const channelLabel = useChannelLabel();
  const origin = dossier ? dossier.origin : receipt;
  const { busy, detailsCard, entryVisit, onSaveNote, onNoteDirty, ...supporting } = annotations;
  const channel = origin?.channel;
  const Icon = channel ? CHANNEL_ICON[channel] : null;
  return (
    <div className={styles.stack} data-testid="dossier-details">
      <DossierCard title={t("business.dossier.details.origin")}>
        <DossierRows>
          <Row fact="channel" label={t("business.dossier.details.channel")} value={channel ? channelLabel(channel) : null} icon={Icon ? <Icon size={16} aria-hidden="true" /> : null} />
          <Row fact="sent_by" label={t("business.dossier.details.sent_by")} value={origin?.sent_by ? sentByName(t, origin.sent_by) : null} />
          <Row fact="received_at" label={t("business.dossier.details.arrived")} value={origin?.received_at ? formatTimestamp(origin.received_at, locale) : null} />
        </DossierRows>
      </DossierCard>
      {dossier ? <DossierNoteCard key={`note-${dossier.draft_id}`} busy={busy} dossier={dossier} detailsCard={detailsCard} entryVisit={entryVisit} onSaveNote={onSaveNote} onNoteDirty={onNoteDirty} /> : null}
      {dossier || detailsCard === "support" ? <DossierSupportingCard key={`support-${dossier?.draft_id ?? "receipt"}`} busy={busy} dossier={dossier} detailsCard={detailsCard} entryVisit={entryVisit} {...supporting} /> : null}
      <DossierCard title={t("business.dossier.details.file")}>
        <DossierRows>
          <Row fact="filename" label={t("business.dossier.details.name")} value={origin?.filename} />
          <Row fact="size" label={t("business.dossier.details.size")} value={origin?.size_bytes != null ? dossierFileSize(origin.size_bytes, locale) : null} />
        </DossierRows>
      </DossierCard>
    </div>
  );
}
