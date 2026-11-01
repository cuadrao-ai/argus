import type { Metadata } from "next";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { Landing } from "@/components/landing/landing";
import { landingPreviewAllowed } from "@/lib/landing-preview";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { absolute: "Cuadrao" },
  robots: { index: false, follow: false },
};

type Props = { params: Promise<{ locale: string }> };

export default async function LandingPreview({ params }: Props) {
  const { locale } = await params;
  const request = await headers();
  const host = request.get("x-forwarded-host") ?? request.get("host");
  if (locale !== "es" || !landingPreviewAllowed(host, process.env.CUADRAO_SITE_INDEXING)) notFound();
  return <Landing locale={locale} />;
}
