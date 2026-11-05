import { WEB_APP_NAME } from "@/lib/app-brand";
import type { Metadata } from "next";
import { headers } from "next/headers";
import ReceiptFollowup from "@/components/receipt/ReceiptFollowup";
import ReceiptBody from "@/components/receipt/ReceiptBody";
import ReceiptNotice from "@/components/receipt/ReceiptNotice";
import { evidenceReceiptSharingEnabled } from "@/lib/private-alpha-flags";
import {
  readPublicReceipt,
  type PublicReceiptResult,
} from "@/lib/public-receipt-contract";
import {
  receiptCopy,
  receiptLanguageFromAcceptLanguage,
} from "@/lib/receipt-copy";
import { notFound } from "next/navigation";
import { receiptDocumentKind } from "@/lib/public-receipt-turns";
import { receiptPreviewFacts } from "@/lib/receipt-preview-facts";

// Revocation has to take effect on the next request, so nothing here is cached
// and nothing is prerendered.
export const dynamic = "force-dynamic";
export const revalidate = 0;

// Permanent, and there is no product surface that can change it. Repeated on the
// page as well as the layout so neither file can quietly drop it.
const RECEIPT_ROBOTS: Metadata["robots"] = {
  index: false,
  follow: false,
  nocache: true,
  googleBot: { index: false, follow: false, noimageindex: true },
};

type ReceiptPageProps = {
  params: Promise<{ receiptId: string }>;
};

// Needed so the preview image resolves to an absolute url in the card markup.
function metadataBase(): URL | undefined {
  const origin = process.env.ARGUS_APP_ORIGIN?.trim();
  if (!origin) return undefined;
  try {
    return new URL(origin);
  } catch {
    return undefined;
  }
}

async function resolveLanguage() {
  const requestHeaders = await headers();
  return receiptLanguageFromAcceptLanguage(
    requestHeaders.get("accept-language"),
  );
}

export async function generateMetadata({
  params,
}: ReceiptPageProps): Promise<Metadata> {
  if (!evidenceReceiptSharingEnabled) {
    return { title: WEB_APP_NAME, robots: RECEIPT_ROBOTS };
  }
  const { receiptId } = await params;
  const language = await resolveLanguage();
  const copy = receiptCopy(language);
  const result = await readPublicReceipt(receiptId);
  // Metadata is cached by the platforms that read it, so a transient failure gets
  // no claim at all rather than a permanent-sounding one. Titling an outage "this
  // one is gone" would pin that on a live receipt.
  if (result.kind === "unavailable") {
    return { title: WEB_APP_NAME, robots: RECEIPT_ROBOTS };
  }
  if (result.kind === "revoked") {
    return {
      title: copy.tombstone.title,
      description: copy.tombstone.detail,
      robots: RECEIPT_ROBOTS,
      metadataBase: metadataBase(),
    };
  }
  const facts = receiptPreviewFacts(result.payload, language);
  const description = facts.description;
  return {
    title: `${facts.title} · ${copy.provenance}`,
    description,
    robots: RECEIPT_ROBOTS,
    metadataBase: metadataBase(),
    openGraph: {
      type: "article",
      title: facts.title,
      description,
      siteName: WEB_APP_NAME,
    },
    twitter: {
      card: "summary_large_image",
      title: facts.title,
      description,
    },
  };
}

export default async function PublicReceiptPage({ params }: ReceiptPageProps) {
  if (!evidenceReceiptSharingEnabled) {
    notFound();
  }
  const { receiptId } = await params;
  const language = await resolveLanguage();
  const copy = receiptCopy(language);
  const result: PublicReceiptResult = await readPublicReceipt(receiptId);

  if (result.kind !== "available") {
    return (
      <div lang={language}>
        <ReceiptNotice kind={result.kind} copy={copy} />
      </div>
    );
  }

  return (
    <div lang={language}>
      <ReceiptBody
        payload={result.payload}
        createdAt={result.createdAt}
        copy={copy}
        language={language}
        footer={<ReceiptFollowup publicId={receiptId} copy={copy} language={language} kind={receiptDocumentKind(result.payload)} />}
      />
    </div>
  );
}
