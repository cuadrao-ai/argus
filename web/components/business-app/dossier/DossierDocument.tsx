"use client";

import { lazy, Suspense, type ReactNode } from "react";
import { Download, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { useBusiness } from "../BusinessWorkspace";
import { DelayedSourceWell } from "../business-skeletons";
import { quietButtonClass, secondaryButtonClass, useChannelLabel } from "../business-ui";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import motion from "../receipt-reading.module.css";
import { useReceiptSource } from "../ReceiptSourcePreview";
import styles from "./dossier.module.css";

const ReceiptImageZoom = lazy(() => import("../ReceiptImageZoom"));

export type DossierFile = Pick<ReceiptSummary, "id" | "media_type" | "filename"> & Partial<Pick<ReceiptSummary, "channel" | "email_delivery_ids">>;

function FileStage({ file, reading }: { file: DossierFile; reading: boolean }) {
  const { t } = useTranslation();
  const { source } = useBusiness();
  const { current, reload } = useReceiptSource(file.id);
  const viewable = file.media_type === "application/pdf" || file.media_type.startsWith("image/") || source.mode === "fixture";
  return <>
    <div className={`${styles.docFill} ${motion.stage}`} data-testid="receipt-original-source">
      {reading ? <span className={motion.ripple} aria-hidden="true" data-testid="receipt-reading-ripple" /> : null}
      {current.kind === "failed" ? (
        <div className="p-5 text-center">
          <p role="alert" className={styles.note}>{t("business.review.source_error", "We couldn't open the original receipt with your current access.")}</p>
          <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={reload}><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("business.dossier.retry_source", "Try opening again")}</button>
        </div>
      ) : current.kind === "loading" ? <DelayedSourceWell />
        : viewable ? <Suspense fallback={<DelayedSourceWell />}><ReceiptImageZoom reading={reading} src={current.url} blob={current.blob} sourceId={current.sourceId} pdf={file.media_type === "application/pdf" && source.mode === "live"} alt={t("business.review.source", "Original receipt")} /></Suspense>
        : <p className={styles.note}>{t("business.dossier.download_source", "Download the original to read this file.")}</p>}
    </div>
    <DocumentFoot file={file} url={current.kind === "ready" ? current.url : null} />
  </>;
}

/**
 * Under the document: the channel's icon and word beside the file name, and the
 * download of the file on screen. A file that came by email offers its email,
 * and says so when it arrived more than once.
 */
function DocumentFoot({ file, url }: { file: DossierFile; url: string | null }) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const channelLabel = useChannelLabel();
  const Icon = file.channel ? CHANNEL_ICON[file.channel] : null;
  const name = file.filename ?? t("business.review.source", "Original receipt");
  const deliveries = file.email_delivery_ids?.length ?? 0;
  // The API lists deliveries earliest first; the first one is where the file first arrived by email.
  const firstEmail = file.email_delivery_ids?.[0];
  const seeEmail = (label: string, testId?: string) => firstEmail ? <button type="button" data-testid={testId} className={quietButtonClass} onClick={() => openPanel({ kind: "email", emailId: firstEmail })}>{label}</button> : null;
  return <>
    {deliveries > 1 ? <p className={`${styles.note} px-3.5 pb-2`} data-testid="receipt-email-times">{t("business.dossier.email_times", { count: deliveries, defaultValue: "This file arrived {{count}} times by email." })}{file.channel !== "email" ? <>{" "}{seeEmail(t("business.dossier.see_first_email", "See the first email"))}</> : null}</p> : null}
    <div className={styles.docFoot} data-testid="dossier-document-foot">
      <span className={styles.docName}>
        {Icon && file.channel ? <><Icon size={15} aria-hidden="true" className="shrink-0" /><span className="whitespace-nowrap" data-testid="receipt-source-channel">{file.channel === "email" ? t("business.dossier.arrived_by_email", "Arrived by email") : channelLabel(file.channel)}{file.channel === "email" && firstEmail ? <>{" · "}{seeEmail(t("business.dossier.see_email", "See email"), "receipt-see-email")}</> : null}</span><span aria-hidden="true">·</span></> : null}
        <span className={styles.docFile} title={name}>{name}</span>
      </span>
      {url ? <a href={url} download={file.filename ?? "receipt"} className={styles.docLink} aria-label={t("business.dossier.document.download", { name })}><Download size={16} aria-hidden="true" />{t("business.review.download", "Download")}</a> : null}
    </div>
  </>;
}

/**
 * The document side: the original on a dot grid, with the viewer's own controls
 * and its file line. `children` shows in its place when the record has no file
 * (a message, or the line that says there is none), and `extra` follows the file.
 */
export default function DossierDocument({ file, children, extra, reading = false }: { file?: DossierFile | null; children?: ReactNode; extra?: ReactNode; /** A read is running: the band sweeps the original. */ reading?: boolean }) {
  const { t } = useTranslation();
  return (
    <section className={`${styles.scope} ${styles.doc}`} aria-label={t("business.dossier.document.region")} data-testid="receipt-review-source">
      {file ? <FileStage key={file.id} file={file} reading={reading} /> : null}
      <div className={styles.docStage} data-beside-file={file ? true : undefined}>{children}{extra}</div>
    </section>
  );
}
