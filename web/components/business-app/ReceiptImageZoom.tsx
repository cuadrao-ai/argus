"use client";

import Image from "next/image";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { ChevronLeft, ChevronRight, ExternalLink, Maximize, Minimize, RotateCcw, RotateCw, ZoomIn, ZoomOut } from "lucide-react";
import { useTranslation } from "react-i18next";
import { readStored, writeStored } from "@/lib/browser-storage";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { Tooltip } from "@/components/ui/Tooltip";
import { loadReceiptPdf, type ReceiptPdf } from "./receipt-pdf-renderer";
import { DelayedSourceWell } from "./business-skeletons";
import motion from "./receipt-reading.module.css";

type Size = { width: number; height: number };
type Point = { x: number; y: number };
type Zoom = { kind: "fit-page" | "fit-width" } | { kind: "manual"; scale: number };
type RotationEntry = { id: string; turns: number };
const ROTATIONS_KEY = "cuadrao:receipt_rotations:v1";
const CONTROL_CLASS = "flex h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-[#172b26] hover:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] disabled:opacity-40 dark:text-white dark:hover:bg-white/[0.06]";

export function readReceiptRotations(): RotationEntry[] {
  try {
    const value: unknown = JSON.parse(readStored(ROTATIONS_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    const entries = new Map<string, RotationEntry>();
    for (const entry of value) {
      if (!entry || typeof entry !== "object" || typeof entry.id !== "string" || !entry.id || !Number.isInteger(entry.turns) || entry.turns < 0 || entry.turns > 3) continue;
      entries.delete(entry.id);
      entries.set(entry.id, { id: entry.id, turns: entry.turns });
    }
    return [...entries.values()].slice(-200);
  } catch { return []; }
}

export function rememberReceiptRotation(id: string, turns?: number): number {
  const entries = readReceiptRotations();
  const previous = entries.find((entry) => entry.id === id)?.turns ?? 0;
  const normalized = turns === undefined ? previous : ((turns % 4) + 4) % 4;
  writeStored(ROTATIONS_KEY, JSON.stringify([...entries.filter((entry) => entry.id !== id), { id, turns: normalized }].slice(-200)));
  return normalized;
}

export function receiptScale(zoom: Zoom, image: Size, viewport: Size, turns: number): number {
  const rotated = Math.abs(turns % 2) === 1;
  const width = rotated ? image.height : image.width;
  const height = rotated ? image.width : image.height;
  if (zoom.kind === "manual") return Math.max(0.25, Math.min(5, zoom.scale));
  return zoom.kind === "fit-width" ? viewport.width / width : Math.min(viewport.width / width, viewport.height / height);
}

function ViewerControl({ label, keys, children, onClick, disabled = false }: { label: string; keys: string; children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return <Tooltip content={`${label}${keys ? ` (${keys})` : ""}`} side="top"><button type="button" className={CONTROL_CLASS} aria-label={label} data-viewer-focus={label} disabled={disabled} onClick={onClick}>{children}</button></Tooltip>;
}

type ViewerProps = { src: string; blob: Blob; sourceId: string; alt: string; pdf?: boolean; reading?: boolean };

export default function ReceiptImageZoom(props: ViewerProps) {
  return <ReceiptViewer key={props.sourceId} {...props} />;
}

function ReceiptViewer({ src, blob, sourceId, alt, pdf = false, reading = false }: ViewerProps) {
  const { t } = useTranslation();
  const label = (key: string) => t(`business.dossier.viewer.${key}`);
  const [zoom, setZoom] = useState<Zoom>({ kind: "fit-page" });
  const [turns, setTurns] = useState(0);
  const [image, setImage] = useState<Size>({ width: 1, height: 1 });
  const [viewport, setViewport] = useState<Size>({ width: 1, height: 1 });
  const [presentation, setPresentation] = useState<"inline" | "overlay">("inline");
  const [originalUrl, setOriginalUrl] = useState<string>();
  const [dragging, setDragging] = useState(false);
  const [pdfDocument, setPdfDocument] = useState<ReceiptPdf | null>(null);
  const [page, setPage] = useState(1);
  const [drawnPage, setDrawnPage] = useState(0);
  const [pdfError, setPdfError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const inlineRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const wellRef = useRef<HTMLDivElement>(null);
  const fullScreenRef = useRef<HTMLButtonElement>(null);
  const anchor = useRef<{ point: Point; x: number; y: number } | null>(null);
  const pointers = useRef(new Map<number, Point>());
  const returnFocusRef = useRef<HTMLElement>(null);
  const openerKey = useRef("fullscreen");
  const overlay = presentation === "overlay";
  const scale = receiptScale(zoom, image, viewport, turns);
  const fitScale = receiptScale({ kind: "fit-page" }, image, viewport, turns);
  const rotated = Math.abs(turns % 2) === 1;
  const width = (rotated ? image.height : image.width) * scale;
  const height = (rotated ? image.width : image.height) * scale;
  const oversize = width > viewport.width || height > viewport.height;
  const closeOverlay = useCallback(() => setPresentation("inline"), []);

  useEffect(() => {
    if (!pdf) return;
    const controller = new AbortController();
    let loaded: ReceiptPdf | undefined;
    setPdfDocument(null);
    setPdfError(false);
    setDrawnPage(0);
    setPage(1);
    void loadReceiptPdf(blob, controller.signal).then(value => {
      loaded = value;
      if (controller.signal.aborted) { void value.destroy(); return; }
      setPdfDocument(value);
    }).catch(() => { if (!controller.signal.aborted) setPdfError(true); });
    return () => { controller.abort(); void loaded?.destroy(); };
  }, [blob, pdf, attempt]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!pdfDocument || !canvas) return;
    const controller = new AbortController();
    setPdfError(false);
    void pdfDocument.drawPage(page, canvas, scale, controller.signal).then(size => {
      if (controller.signal.aborted) return;
      setImage(previous => previous.width === size.width && previous.height === size.height ? previous : size);
      setDrawnPage(page);
    }).catch(() => { if (!controller.signal.aborted) setPdfError(true); });
    return () => controller.abort();
  }, [pdfDocument, page, scale, presentation]);

  useLayoutEffect(() => {
    if (overlay) return;
    returnFocusRef.current = [...(inlineRef.current?.querySelectorAll<HTMLElement>("[data-viewer-focus]") ?? [])].find((node) => node.dataset.viewerFocus === openerKey.current) ?? inlineRef.current;
  }, [overlay]);

  useEffect(() => { setTurns(rememberReceiptRotation(sourceId)); }, [sourceId]);
  useEffect(() => {
    const url = URL.createObjectURL(blob);
    setOriginalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  useLayoutEffect(() => {
    const well = wellRef.current;
    if (!well) return;
    const measure = () => setViewport({ width: Math.max(1, well.clientWidth), height: Math.max(1, well.clientHeight) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(well);
    return () => observer.disconnect();
  }, [presentation]);

  const changeZoom = useCallback((next: Zoom, point?: Point, destination?: Point) => {
    if (next.kind === "manual") {
      if (next.scale === scale) next = zoom;
      else if (next.scale < scale && scale <= 0.25 && fitScale < 0.25) next = { kind: "fit-page" };
      else next = { kind: "manual", scale: receiptScale(next, image, viewport, turns) };
    }
    const well = wellRef.current;
    if (receiptScale(next, image, viewport, turns) === scale) {
      if (well && point && destination) {
        well.scrollLeft -= destination.x - point.x;
        well.scrollTop -= destination.y - point.y;
      }
      anchor.current = null;
      setZoom(next);
      return;
    }
    if (well) {
      const box = well.getBoundingClientRect();
      const position = point ? { x: point.x - box.left, y: point.y - box.top } : { x: well.clientWidth / 2, y: well.clientHeight / 2 };
      anchor.current = { point: destination ? { x: destination.x - box.left, y: destination.y - box.top } : position, x: (well.scrollLeft + position.x - Math.max(0, (well.clientWidth - width) / 2)) / scale, y: (well.scrollTop + position.y - Math.max(0, (well.clientHeight - height) / 2)) / scale };
    }
    setZoom(next);
  }, [width, height, scale, image, viewport, turns, fitScale, zoom]);

  useLayoutEffect(() => {
    const well = wellRef.current;
    const pending = anchor.current;
    if (!well || !pending) return;
    well.scrollLeft = pending.x * scale + Math.max(0, (well.clientWidth - width) / 2) - pending.point.x;
    well.scrollTop = pending.y * scale + Math.max(0, (well.clientHeight - height) / 2) - pending.point.y;
    anchor.current = null;
  }, [scale, width, height]);

  useEffect(() => {
    const well = wellRef.current;
    if (!well) return;
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      changeZoom({ kind: "manual", scale: scale * Math.exp(-event.deltaY * 0.01) }, { x: event.clientX, y: event.clientY });
    };
    well.addEventListener("wheel", wheel, { passive: false });
    return () => well.removeEventListener("wheel", wheel);
  }, [changeZoom, scale, presentation]);

  const rotate = (direction: number) => {
    anchor.current = null;
    const next = turns + direction;
    setTurns(next);
    rememberReceiptRotation(sourceId, next);
  };
  const step = (direction: number) => changeZoom({ kind: "manual", scale: Math.round((scale + direction * 0.25) * 100) / 100 });
  const cycleFit = () => changeZoom(zoom.kind === "fit-page" ? { kind: "fit-width" } : zoom.kind === "fit-width" ? { kind: "manual", scale: 1 } : { kind: "fit-page" });
  const toggleOverlay = () => {
    if (!overlay) openerKey.current = (document.activeElement as HTMLElement | null)?.dataset.viewerFocus ?? "fullscreen";
    setPresentation(overlay ? "inline" : "overlay");
  };
  const shortcut = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || (event.target instanceof HTMLElement && event.target.isContentEditable)) return;
    const key = event.key.toLowerCase();
    if (key === "r") rotate(event.shiftKey ? -1 : 1);
    else if (key === "+" || key === "=") step(1);
    else if (key === "-") step(-1);
    else if (key === "0") changeZoom({ kind: "fit-page" });
    else if (key === "f") toggleOverlay();
    else if (key === "escape" && overlay) closeOverlay();
    else return;
    event.preventDefault();
    event.stopPropagation();
  };
  const pointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && (event.button !== 0 || !oversize)) return;
    event.currentTarget.focus({ preventScroll: true });
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    setDragging(true);
  };
  const pointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const previous = pointers.current.get(event.pointerId);
    const well = wellRef.current;
    if (!previous || !well) return;
    const next = { x: event.clientX, y: event.clientY };
    const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
    if (other) {
      const distance = Math.hypot(previous.x - other.x, previous.y - other.y);
      const nextDistance = Math.hypot(next.x - other.x, next.y - other.y);
      if (distance > 0) changeZoom({ kind: "manual", scale: scale * nextDistance / distance }, { x: (previous.x + other.x) / 2, y: (previous.y + other.y) / 2 }, { x: (next.x + other.x) / 2, y: (next.y + other.y) / 2 });
    }
    if (!other) {
      well.scrollLeft -= next.x - previous.x;
      well.scrollTop -= next.y - previous.y;
    }
    pointers.current.set(event.pointerId, next);
  };
  const pointerEnd = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointers.current.delete(event.pointerId);
    if (!pointers.current.size) setDragging(false);
  };
  const cancelGesture = () => {
    pointers.current.clear();
    setDragging(false);
  };
  const paperStyle = { left: "50%", top: "50%", width: image.width * scale, height: image.height * scale, maxWidth: "none", transform: `translate(-50%, -50%) rotate(${turns * 90}deg)` };
  const paperClass = "absolute select-none transition-transform duration-150 motion-reduce:transition-none";
  const content = (
    <div ref={surfaceRef} role={overlay ? "dialog" : undefined} aria-modal={overlay ? true : undefined} aria-label={alt} tabIndex={-1} onKeyDown={shortcut} className={overlay ? "fixed inset-0 z-[9000] bg-black/90 p-3" : "relative w-full"} data-testid={overlay ? "receipt-viewer-overlay" : "receipt-viewer"}>
      <div ref={wellRef} data-viewer-focus="well" data-testid="receipt-image-zoom" data-zoom={scale} data-rotation={((turns % 4) + 4) % 4 * 90} data-fit={zoom.kind} tabIndex={0} aria-label={alt} className={`${overlay ? "h-[calc(100dvh-84px)]" : "h-[300px] desktop:h-[520px]"} w-full overflow-auto overscroll-contain rounded-item focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49]`} style={{ touchAction: "none", cursor: oversize ? dragging ? "grabbing" : "grab" : "default" }} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerEnd} onPointerCancel={cancelGesture} onLostPointerCapture={pointerEnd} onDoubleClick={(event) => changeZoom(scale >= 5 ? { kind: "fit-page" } : { kind: "manual", scale: Math.min(5, scale * 2) }, { x: event.clientX, y: event.clientY })}>
        <div style={{ width: Math.max(width, viewport.width), height: Math.max(height, viewport.height), position: "relative" }}>
          {pdf
            ? <canvas ref={canvasRef} role="img" aria-label={t("business.transactions.pagination.page", { page })} data-page={drawnPage} className={paperClass} style={{ ...paperStyle, visibility: drawnPage === page && !pdfError ? "visible" : "hidden" }} />
            : <Image unoptimized draggable={false} src={src} width={image.width} height={image.height} alt={alt} onLoad={(event) => { const loaded = event.currentTarget; setImage({ width: loaded.naturalWidth, height: loaded.naturalHeight }); }} className={paperClass} style={paperStyle} />}
          {reading && (!pdf || drawnPage === page && !pdfError) ? (
            <div aria-hidden="true" className={`${paperClass} pointer-events-none overflow-hidden`} style={paperStyle}>
              <span className={motion.scan} data-testid="receipt-reading-band" />
            </div>
          ) : null}
        </div>
      </div>
      {pdf && (pdfError || drawnPage !== page) ? <div className="pointer-events-none absolute inset-x-0 top-0 flex h-[calc(100%-64px)] items-center justify-center p-5 text-center">
        {pdfError ? <div className="pointer-events-auto"><p role="alert">{t("business.review.source_error")}</p><button type="button" className="min-h-11 underline" onClick={() => setAttempt(value => value + 1)}>{t("business.dossier.retry_source")}</button></div> : <DelayedSourceWell />}
      </div> : null}
      <div className="absolute bottom-2 left-1/2 flex max-w-[calc(100%-8px)] -translate-x-1/2 items-center overflow-x-auto rounded-full border border-[#DCE0DA] bg-[#FFFEFA] p-1 dark:border-white/10 dark:bg-[#1f2225]" data-testid="receipt-viewer-toolbar">
        {pdfDocument && pdfDocument.pageCount > 1 ? <>
          <ViewerControl label={t("business.transactions.pagination.previous")} keys="" disabled={page === 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={18} aria-hidden="true" /></ViewerControl>
          <span className="shrink-0 text-[14px] tabular-nums" aria-live="polite">{page}/{pdfDocument.pageCount}</span>
          <ViewerControl label={t("business.transactions.pagination.next")} keys="" disabled={page === pdfDocument.pageCount} onClick={() => setPage(value => value + 1)}><ChevronRight size={18} aria-hidden="true" /></ViewerControl>
        </> : null}
        <ViewerControl label={label("rotate_left")} keys="Shift+R" onClick={() => rotate(-1)}><RotateCcw size={18} aria-hidden="true" /></ViewerControl>
        <ViewerControl label={label("rotate_right")} keys="R" onClick={() => rotate(1)}><RotateCw size={18} aria-hidden="true" /></ViewerControl>
        <ViewerControl label={label("zoom_out")} keys="-" onClick={() => step(-1)} disabled={scale <= Math.min(0.25, fitScale)}><ZoomOut size={18} aria-hidden="true" /></ViewerControl>
        <Tooltip content={`${label(zoom.kind === "fit-page" ? "fit_width" : zoom.kind === "fit-width" ? "actual_size" : "fit_page")} (${zoom.kind === "manual" ? "0" : "Enter"})`} side="top"><button type="button" data-viewer-focus="fit" onClick={cycleFit} aria-label={label(zoom.kind === "fit-page" ? "fit_width" : zoom.kind === "fit-width" ? "actual_size" : "fit_page")} className={`${CONTROL_CLASS} min-w-14 text-[14px] tabular-nums`}><span aria-live="polite">{Math.round(scale * 100)}%</span></button></Tooltip>
        <ViewerControl label={label("zoom_in")} keys="+" onClick={() => step(1)} disabled={scale >= 5}><ZoomIn size={18} aria-hidden="true" /></ViewerControl>
        <Tooltip content={`${label(overlay ? "exit_full_screen" : "full_screen")} (F${overlay ? ", Esc" : ""})`} side="top"><button ref={fullScreenRef} data-viewer-focus="fullscreen" type="button" className={CONTROL_CLASS} aria-label={label(overlay ? "exit_full_screen" : "full_screen")} onClick={toggleOverlay}>{overlay ? <Minimize size={18} aria-hidden="true" /> : <Maximize size={18} aria-hidden="true" />}</button></Tooltip>
        <Tooltip content={`${label("open_original")} (Enter)`} side="top"><a data-viewer-focus="original" href={originalUrl} target="_blank" rel="noopener noreferrer" className={CONTROL_CLASS} aria-label={label("open_original")}><ExternalLink size={18} aria-hidden="true" /></a></Tooltip>
      </div>
    </div>
  );
  return <div ref={inlineRef} tabIndex={-1} className="w-full">{overlay ? <FullWindow surfaceRef={surfaceRef} initialFocusRef={fullScreenRef} returnFocusRef={returnFocusRef} onDismiss={closeOverlay}>{content}</FullWindow> : content}</div>;
}

const FullWindow = withViewportPortal(function FullWindow({ children, surfaceRef, initialFocusRef, returnFocusRef, onDismiss }: { children: React.ReactNode; surfaceRef: React.RefObject<HTMLDivElement | null>; initialFocusRef: React.RefObject<HTMLButtonElement | null>; returnFocusRef: React.RefObject<HTMLElement | null>; onDismiss: () => void }) {
  const overlayId = useId();
  useModalSurface({ isOpen: true, overlayId, containerRef: surfaceRef, onDismiss, initialFocusRef, returnFocusRef });
  return children;
});
