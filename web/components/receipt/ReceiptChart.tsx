"use client";

import { useEffect, useRef, useState } from "react";
import {
  BaselineSeries,
  ColorType,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import type { EvidenceVisual } from "@/lib/evidence-visual";
import { CHART_ATTRIBUTION_LABEL, CHART_ATTRIBUTION_NOTICE, CHART_ATTRIBUTION_URL } from "@/lib/chart-attribution";

type ReceiptChartProps = {
  visual: EvidenceVisual;
};

const POSITIVE_LINE = "#5ba897";
const NEGATIVE_LINE = "#c67378";

function chartTime(value: string): UTCTimestamp | string {
  // Daily points stay as business days so the axis reads as dates, not clocks.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return Math.floor(parsed / 1000) as UTCTimestamp;
}

function documentIsDark(): boolean {
  if (typeof document === "undefined") return true;
  return document.documentElement.classList.contains("dark");
}

/**
 * A read-only chart of frozen data. No range controls, no tooltip, no markers:
 * a receipt is a record, and the numbers a viewer needs are in the metric rows
 * beside it.
 *
 * Appearance is read from the document class rather than a prop, because the
 * page around it is server-rendered and the theme is only known in the browser.
 */
export default function ReceiptChart({ visual }: ReceiptChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    setIsDark(documentIsDark());
    const observer = new MutationObserver(() => setIsDark(documentIsDark()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || visual.series.length < 2) return;
    const chart = createChart(container, {
      autoSize: true,
      height: 220,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: isDark ? "rgba(255,255,255,0.42)" : "rgba(0,0,0,0.45)",
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "transparent" },
        horzLines: { color: "transparent" },
      },
      // No price axis and no time axis. The axis showed raw portfolio floats
      // ("10800.00") against tick labels that read "2 5 8", which told a reader
      // nothing the return figure above has not already told them. The window's
      // endpoints are rendered under the chart as dates instead.
      rightPriceScale: {
        visible: false,
        borderVisible: false,
        scaleMargins: { top: 0.12, bottom: 0.06 },
      },
      leftPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false, secondsVisible: false },
      handleScroll: false,
      handleScale: false,
      crosshair: { horzLine: { visible: false }, vertLine: { visible: false } },
    });
    const baseValue = visual.base_value ?? visual.series[0]?.value ?? 0;
    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: baseValue },
      lineWidth: 2,
      topLineColor: POSITIVE_LINE,
      bottomLineColor: NEGATIVE_LINE,
      topFillColor1: "rgba(91, 168, 151, 0.28)",
      topFillColor2: "rgba(91, 168, 151, 0.00)",
      bottomFillColor1: "rgba(198, 115, 120, 0.24)",
      bottomFillColor2: "rgba(198, 115, 120, 0.00)",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    series.setData(
      visual.series.map((point) => ({
        time: chartTime(point.time),
        value: point.value,
      })),
    );
    // autoSize means the container can still be zero-width on this tick, and
    // fitContent against a zero width leaves the series bunched into a corner.
    // Fit once the browser has laid the container out, and again whenever it
    // changes size.
    const fit = () => chart.timeScale().fitContent();
    const frame = requestAnimationFrame(fit);
    const observer = new ResizeObserver(fit);
    observer.observe(container);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      chart.remove();
    };
  }, [visual, isDark]);

  return <div>
    <div ref={containerRef} className="h-[220px] w-full" />
    <div data-testid="receipt-chart-attribution" className="border-t border-black/[0.04] pb-2 pt-1.5 text-[10px] leading-snug text-black/45 dark:border-white/[0.06] dark:text-white/45">
      <a href={CHART_ATTRIBUTION_URL} target="_blank" rel="noreferrer" className="inline-flex max-w-full text-inherit underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:focus-visible:ring-white/30">
        {CHART_ATTRIBUTION_LABEL}™
      </a>
      <p>{CHART_ATTRIBUTION_NOTICE}</p>
    </div>
  </div>;
}
