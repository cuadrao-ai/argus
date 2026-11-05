import type { Metadata, Viewport } from "next";
import LandingIntentCapture from "@/components/receipt/LandingIntentCapture";

/** Public frozen conversation shell. Noindex applies to every shared route. */
export const viewport: Viewport = {
  // The action bar sits against the bottom edge, so it has to know how tall the iOS
  // home indicator is. env(safe-area-inset-*) reports zero unless the viewport opts
  // into the full screen, and this is set on the receipt route only: the app shell's
  // own viewport belongs to the responsive-shell lane.
  viewportFit: "cover",
};

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: { index: false, follow: false, noimageindex: true },
  },
};

export default function PublicReceiptLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // Fill the viewport even when the selected thread is short.
    <div className="flex min-h-dvh w-full flex-col bg-white text-black dark:bg-[#191c1f] dark:text-white">
      <LandingIntentCapture />
      {children}
    </div>
  );
}
