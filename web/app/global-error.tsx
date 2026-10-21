"use client";

import { useState } from "react";
import localFont from "next/font/local";

import "./globals.css";
import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { CUADRAO_ADMIN_EMAIL, referenceCode } from "@/lib/failure-screen";
import spanish from "@/public/locales/es-419/common.json";

const inter = localFont({
  src: "./fonts/InterVariable.woff2",
  variable: "--font-inter",
  weight: "100 900",
});

const spaceGrotesk = localFont({
  src: "./fonts/SpaceGrotesk[wght].woff2",
  variable: "--font-space-grotesk",
  weight: "300 700",
});

const copy = spanish.auth.screen;

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [reference] = useState(() => referenceCode(error));
  return (
    <html lang="es-419" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <body className="font-sans antialiased">
        <BrandedStatusScreen
          testId="server-error-screen"
          title={copy.server_title}
          actionLabel={copy.try_again}
          onAction={reset}
          secondaryLabel={copy.go_home}
          secondaryHref="/?auth=login"
          reference={reference}
          contactEmail={CUADRAO_ADMIN_EMAIL}
        />
      </body>
    </html>
  );
}
