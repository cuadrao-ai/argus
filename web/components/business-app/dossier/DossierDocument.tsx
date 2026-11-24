"use client";

import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Download, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessSupportingFile } from "@/lib/business-dossier";
import type { ReceiptSummary } from "@/lib/business-api";
import { useBusiness } from "../BusinessWorkspace";
import { DelayedSourceWell } from "../business-skeletons";
import { quietButtonClass, secondaryButtonClass, useChannelLabel } from "../business-ui";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import motion from "../receipt-reading.module.css";
import { useReceiptSource, type ReceiptSourceState } from "../ReceiptSourcePreview";
import compareStyles from "./compare.module.css";
import styles from "./dossier.module.css";

const ReceiptImageZoom = lazy(() => import("../ReceiptImageZoom"));

export type DossierFile = Pick<ReceiptSummary, "id" | "media_type" | "filename"> & Partial<Pick<ReceiptSummary, "channel" | "email_delivery_ids">> & { supporting?: boolean };

type ReadFile = (id: string, signal: AbortSignal) => Promise<Blob>;

function usePreviewKind(file: DossierFile) {
  const { source } = useBusiness();
  if (source.mode === "fixture" || file.media_type.startsWith("image/")) return "image";
  return file.media_type === "application/pdf" ? "pdf" : "download";
}

function FilePreview({ file, kind, current, reload, reading }: {
  file: DossierFile; kind: ReturnType<typeof usePreviewKind>; current: ReceiptSourceState; reload: () => void; reading: boolean;
}) {
  const { t } = useTranslation();
  return <>
    {reading ? <span className={motion.ripple} aria-hidden="true" data-testid="receipt-reading-ripple" /> : null}
    {current.kind === "failed" ? (
      <div className="p-5 text-center">
        <p role="alert" className={styles.note}>{t("business.review.source_error", "We couldn't open the original receipt with your current access.")}</p>
        <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={reload}><RotateCcw className="h-4 w-4" aria-hidden="true" />{t("business.dossier.retry_source", "Try opening again")}</button>
      </div>
    ) : current.kind === "loading" ? <DelayedSourceWell />
      : kind !== "download" ? <Suspense fallback={<DelayedSourceWell />}><ReceiptImageZoom reading={reading} src={current.url} blob={current.blob} sourceId={current.sourceId} pdf={kind === "pdf"} alt={file.supporting ? file.filename ?? t("business.dossier.supporting.document_label") : t("business.review.source", "Original receipt")} /></Suspense>
      : <p className={styles.note}>{t("business.dossier.download_source", "Download the original to read this file.")}</p>}
  </>;
}

function FileStage({ file, reading, read }: { file: DossierFile; reading: boolean; read?: ReadFile }) {
  const { current, reload } = useReceiptSource(file.id, read);
  const kind = usePreviewKind(file);
  return <>
    <div className={`${styles.docFill} ${motion.stage}`} data-testid="receipt-original-source">
      <FilePreview file={file} kind={kind} current={current} reload={reload} reading={reading} />
    </div>
    <DocumentFoot file={file} url={current.kind === "ready" ? current.url : null} />
  </>;
}

export type CompareSide = "document" | "other";
const COMPARE_SIDES: readonly CompareSide[] = ["document", "other"];
type ComparePreviewStatus = "painted" | "fallback" | undefined;

function CompareFile({ file, side, visible, selected, painted, onSettled }: {
  file: DossierFile;
  side: CompareSide;
  visible: boolean;
  selected: boolean;
  painted: boolean;
  onSettled: (side: CompareSide, status: ComparePreviewStatus) => void;
}) {
  const kind = usePreviewKind(file);
  const { current, reload } = useReceiptSource(file.id);
  const [imageFailed, setImageFailed] = useState(false);
  const layer = useRef<HTMLDivElement>(null);
  const imageLoaded = useCallback((image: HTMLImageElement) => {
    if (!image.naturalWidth || painted) return;
    const show = () => { if (layer.current?.contains(image)) onSettled(side, "painted"); };
    if (typeof image.decode === "function") void image.decode().then(show, show);
    else show();
  }, [onSettled, painted, side]);

  useEffect(() => {
    const node = layer.current;
    if (!node || painted || current.kind === "loading") return;
    if (current.kind === "failed" || kind === "download") {
      onSettled(side, "fallback");
      return;
    }
    const check = () => {
      if (kind === "image") {
        const image = node.querySelector("img");
        if (image?.complete) imageLoaded(image);
      } else if (node.querySelector('[role="alert"]')) {
        onSettled(side, "fallback");
      } else {
        // The PDF viewer publishes the page number after it draws the canvas.
        const drawn = node.querySelector('canvas[data-page]:not([data-page="0"])');
        onSettled(side, drawn ? "painted" : undefined);
      }
    };
    const observer = new MutationObserver(check);
    observer.observe(node, { childList: true, subtree: true, attributeFilter: ["data-page"] });
    check();
    return () => observer.disconnect();
  }, [current.kind, imageLoaded, kind, onSettled, painted, side]);

  return <>
    <div ref={layer} className={`${styles.docFill} ${compareStyles.layer}`} data-visible={visible}
      inert={!selected || !visible} aria-hidden={!selected || !visible ? true : undefined}
      onLoadCapture={event => { if (event.target instanceof HTMLImageElement) imageLoaded(event.target); }}
      onErrorCapture={event => {
        if (!(event.target instanceof HTMLImageElement)) return;
        setImageFailed(true);
        onSettled(side, "fallback");
      }}>
      <FilePreview file={file} kind={kind} current={imageFailed ? { kind: "failed" } : current}
        reload={() => { onSettled(side, undefined); setImageFailed(false); reload(); }} reading={false} />
    </div>
    {visible ? <DocumentFoot file={file} url={selected && current.kind === "ready" ? current.url : null} /> : null}
  </>;
}

export function DossierCompareDocument({ files, side, noFile }: {
  files: Record<CompareSide, DossierFile | null>;
  side: CompareSide;
  noFile: ReactNode;
}) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Partial<Record<CompareSide, ComparePreviewStatus>>>({});
  const onSettled = useCallback((key: CompareSide, outcome: ComparePreviewStatus) =>
    setStatus(previous => previous[key] === outcome ? previous : { ...previous, [key]: outcome }), []);
  const opposite = side === "document" ? "other" : "document";
  const waiting = files[side] && !status[side] && status[opposite] === "painted";
  const visible = waiting ? opposite : side;

  return <section className={`${styles.scope} ${styles.doc}`} aria-label={t("business.dossier.document.region")} data-testid="receipt-review-source">
    {waiting ? <span className="sr-only" role="status">{t("common.loading")}</span> : null}
    <div className={compareStyles.preview} data-testid="receipt-original-source">
      {COMPARE_SIDES.map(key => {
        const file = files[key];
        const selected = key === side;
        if (!file) return <div key={key} className={`${styles.docStage} ${compareStyles.layer}`} data-visible={key === visible}
          inert={!selected} aria-hidden={!selected ? true : undefined}>{noFile}</div>;
        if (!selected && !status[key]) return null;
        return <CompareFile key={key} side={key} file={file} selected={selected} visible={key === visible} painted={status[key] === "painted"}
          onSettled={onSettled} />;
      })}
    </div>
  </section>;
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
        {file.supporting ? <><span>{t("business.dossier.supporting.document_label")}</span><span aria-hidden="true">·</span></> : null}
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
export default function DossierDocument({ file, children, extra, reading = false, supporting = [], selected, onPick, readSupport }: {
  readSupport?: ReadFile;
  supporting?: BusinessSupportingFile[];
  selected?: BusinessSupportingFile;
  onPick?: (sourceId: string | null) => void; file?: DossierFile | null; children?: ReactNode; extra?: ReactNode; /** A read is running: the band sweeps the original. */ reading?: boolean }) {
  const { t } = useTranslation();
  const displayed: DossierFile | null | undefined = selected ? {
    id: selected.receipt_id, filename: selected.filename ?? t("business.dossier.supporting.document_label"),
    media_type: selected.media_type ?? "application/octet-stream", supporting: true,
  } : file;
  return (
    <section className={`${styles.scope} ${styles.doc}`} aria-label={t("business.dossier.document.region")} data-testid="receipt-review-source">
      {supporting.length > 0 && onPick ? <div role="group" aria-label={t("business.dossier.supporting.document_selector")} className={`${styles.docStrip} [&_button]:rounded-item`}>
        <button type="button" aria-pressed={!selected} onClick={() => onPick(null)}>{t("business.dossier.supporting.receipt_label")}</button>
        {supporting.map(item => <button type="button" key={item.source_id} aria-pressed={selected?.source_id === item.source_id}
          title={item.filename ?? undefined} onClick={() => onPick(item.source_id)}>{item.filename ?? t("business.dossier.supporting.document_label")}</button>)}
      </div> : null}
      {displayed ? <FileStage key={displayed.id} file={displayed} reading={reading} read={selected ? readSupport : undefined} /> : null}
      <div className={styles.docStage} data-beside-file={file ? true : undefined}>{!selected && <>{children}{extra}</>}</div>
    </section>
  );
}
