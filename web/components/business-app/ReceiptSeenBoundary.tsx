"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptDetail } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { secondaryButtonClass } from "./business-ui";

export default function ReceiptSeenBoundary({ receipt, hydrated }: { receipt: ReceiptDetail; hydrated: boolean }) {
  const { source, reload } = useBusiness();
  const { t } = useTranslation();
  const sentinel = useRef<HTMLDivElement>(null);
  const acknowledged = useRef<string | null>(null);
  const inFlight = useRef<{ id: string; cursor: string } | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const identity = useRef({ id: receipt.id, cursor: receipt.activity?.completion_cursor });
  useLayoutEffect(() => { identity.current = { id: receipt.id, cursor: receipt.activity?.completion_cursor }; }, [receipt.id, receipt.activity?.completion_cursor]);
  const cursor = receipt.activity?.state === "ready" ? receipt.activity.completion_cursor : null;
  const mark = useCallback(async () => {
    if (!hydrated || !cursor || !source.markReceiptRead || (inFlight.current?.id === receipt.id && inFlight.current?.cursor === cursor) || acknowledged.current === cursor) return;
    const request = { id: receipt.id, cursor };
    inFlight.current = request;
    try {
      const result = await source.markReceiptRead(receipt.id, cursor);
      if (mounted.current && identity.current.id === receipt.id && identity.current.cursor === cursor && result.completion_cursor === cursor && !result.unread) { acknowledged.current = cursor; reload(); }
    } catch { /* A failed acknowledgement leaves the server boundary unchanged. */ }
    finally { if (inFlight.current === request) inFlight.current = null; }
  }, [hydrated, cursor, source, receipt.id, reload]);
  useEffect(() => {
    if (!hydrated || !cursor || !sentinel.current) return;
    let intersects = false;
    const visible = () => { if (intersects && document.visibilityState !== "hidden" && document.hasFocus()) void mark(); };
    const observer = new IntersectionObserver((entries) => { intersects = entries.some((entry) => entry.isIntersecting); visible(); });
    observer.observe(sentinel.current);
    window.addEventListener("focus", visible);
    document.addEventListener("visibilitychange", visible);
    return () => { observer.disconnect(); window.removeEventListener("focus", visible); document.removeEventListener("visibilitychange", visible); };
  }, [hydrated, cursor, mark]);
  return <div ref={sentinel} data-testid="receipt-canonical-content">
    {hydrated && receipt.activity?.unread && cursor ? <button type="button" className={secondaryButtonClass} onClick={() => void mark()}>{t("business.activity.mark_read", "Mark as read")}</button> : null}
  </div>;
}
