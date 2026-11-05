import { ImageResponse } from "next/og";
import { evidenceReceiptSharingEnabled } from "@/lib/private-alpha-flags";
import { receiptCopy } from "@/lib/receipt-copy";
import { receiptPreviewFacts } from "@/lib/receipt-preview-facts";
import {
  readPublicReceipt,
} from "@/lib/public-receipt-contract";

/**
 * The preview card, rendered server-side from the frozen snapshot.
 *
 * Why rendered rather than static: a static brand tile would say nothing about
 * the receipt, and an unlabelled card pasted into a thread reads as spam, which
 * kills the distribution loop the card exists to serve. A rendered card also
 * lets the provenance mark be guaranteed by code instead of remembered by
 * whoever drew the asset once.
 *
 * The image is a public artifact and inherits section 3 in full. Its inputs are
 * a named, hard-coded subset of an already sanitized payload, listed in
 * PREVIEW_FIELDS below. It reads no artifact, no run and no conversation, and it
 * makes no provider call: everything on the card is frozen data.
 */
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const runtime = "nodejs";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Tested with Cuadrao";

// The whole of what may appear on the card. Adding to this list is a deliberate
// change to what Argus publishes, and it is asserted by test.
// Deliberately shorter than the page. A 1200 pixel card is displayed in a chat
// bubble around 250 to 320 pixels wide, so everything divides by about four and
// anything under roughly eleven effective pixels is decoration. The title, the
// symbols and the dates came off: platforms render og:title as text beside the
// image, so putting it inside the image only competed with the number.
export const PREVIEW_FIELDS = [
  "headline_metric.value",
  "benchmark_verdict",
] as const;

// The card is a public artifact too: never indexed, and never cached by Argus so
// a revoked receipt stops serving its old card on the next request. Platforms
// that already cached it are the honest limit stated in the product.
const IMAGE_HEADERS = {
  "X-Robots-Tag": "noindex, nofollow, noimageindex",
  "Cache-Control": "no-store, max-age=0",
};

const BACKGROUND = "#191c1f";
const FOREGROUND = "#ffffff";
const MUTED = "rgba(255,255,255,0.52)";
const ACCENT = "#5ba897";
const NEGATIVE = "#d66d75";

// The card follows the receipt's own language, not a viewer's. There is no viewer
// when a crawler fetches it, and the frozen facts on the card are in that language
// already, so anything else produces a mixed-language public artifact.
function cardCopy(language: "en" | "es-419") {
  const copy = receiptCopy(language);
  return {
    framing: copy.framing.short,
    provenance: copy.provenance,
    gone: copy.tombstone.title,
    wordmark: copy.wordmark,
  };
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: BACKGROUND,
        padding: "68px 72px",
        fontFamily: "sans-serif",
      }}
    >
      {children}
    </div>
  );
}

function ProvenanceRow({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <div
        style={{
          width: 16,
          height: 16,
          borderRadius: 999,
          background: ACCENT,
        }}
      />
      <div
        style={{
          fontSize: 24,
          letterSpacing: 2,
          textTransform: "uppercase",
          color: MUTED,
        }}
      >
        {label}
      </div>
    </div>
  );
}

export default async function Image({
  params,
}: {
  params: Promise<{ receiptId: string }>;
}) {
  if (!evidenceReceiptSharingEnabled) {
    return new Response(null, { status: 404 });
  }
  const { receiptId } = await params;
  const result = await readPublicReceipt(receiptId);

  // A transient failure must not become a permanent-looking card. Platforms cache
  // preview images, so rendering "this one is gone" during an outage would leave a
  // revoked-looking card pinned to a receipt that is perfectly alive, and Argus
  // cannot clear a cache it does not own. No body and a retryable status means the
  // platform shows no card and asks again later, which is recoverable.
  if (result.kind === "unavailable") {
    return new Response(null, {
      status: 503,
      headers: { ...IMAGE_HEADERS, "Retry-After": "120" },
    });
  }

  if (result.kind === "revoked") {
    // No payload means no content language to follow, so the tombstone card falls
    // back to English.
    const copy = cardCopy("en");
    return new ImageResponse(
      (
        <Frame>
          <ProvenanceRow label={copy.provenance} />
          <div style={{ display: "flex", fontSize: 52, color: FOREGROUND }}>
            {copy.gone}
          </div>
          <div style={{ display: "flex", fontSize: 26, color: MUTED }}>
            {copy.framing}
          </div>
        </Frame>
      ),
      { ...size, headers: IMAGE_HEADERS },
    );
  }

  const language = result.payload.schema_version === 1 ? result.payload.content_language : result.payload.turns[0].content_language;
  const copy = cardCopy(language);
  const facts = receiptPreviewFacts(result.payload, language);
  if (facts.research) {
    return new ImageResponse((
      <Frame>
        <div style={{ display: "flex", fontSize: 46, fontWeight: 500, letterSpacing: 1, color: FOREGROUND }}>{copy.wordmark}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ display: "flex", fontSize: 62, fontWeight: 500, lineHeight: 1.1, color: FOREGROUND }}>{facts.imageTitle}</div>
          <div style={{ display: "flex", fontSize: 30, color: MUTED }}>{[facts.stamp, facts.countText].filter(Boolean).join(" · ")}</div>
        </div>
        <div style={{ display: "flex", fontSize: 36, color: MUTED }}>{facts.framing}</div>
      </Frame>
    ), { ...size, headers: IMAGE_HEADERS });
  }
  const negative = facts.metricValue.trim().startsWith("-");
  return new ImageResponse(
    (
      <Frame>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              display: "flex",
              width: 26,
              height: 26,
              borderRadius: 999,
              background: ACCENT,
            }}
          />
          <div
            style={{
              display: "flex",
              fontSize: 46,
              fontWeight: 500,
              letterSpacing: 1,
              color: FOREGROUND,
            }}
          >
            {copy.wordmark}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {facts.metricValue ? (
            <div
              style={{
                display: "flex",
                fontSize: 200,
                lineHeight: 0.94,
                fontWeight: 500,
                letterSpacing: -8,
                color: negative ? NEGATIVE : ACCENT,
              }}
            >
              {facts.metricValue}
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {facts.countText && <div style={{ display: "flex", fontSize: 24, color: MUTED }}>{facts.countText}</div>}
          {facts.verdict ? (
            <div
              style={{
                display: "flex",
                fontSize: 56,
                fontWeight: 500,
                letterSpacing: -1,
                color: FOREGROUND,
              }}
            >
              {facts.verdict}
            </div>
          ) : null}
          <div style={{ display: "flex", fontSize: 44, color: MUTED }}>
            {copy.framing}
          </div>
        </div>
      </Frame>
    ),
    { ...size, headers: IMAGE_HEADERS },
  );
}
