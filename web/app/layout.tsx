import type { Metadata, Viewport } from "next";
import { WEB_APP_DESCRIPTION, WEB_APP_NAME } from "@/lib/app-brand";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { THEME_STORAGE_KEY } from "@/lib/browser-storage";
import { I18nProvider } from "@/components/I18nProvider";
import { AuthLinkErrorGate } from "@/components/status/AuthLinkErrorGate";
import localFont from "next/font/local";

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

export const metadata: Metadata = {
  title: WEB_APP_NAME,
  description: WEB_APP_DESCRIPTION,
  manifest: "/manifest.json",
  // iOS ignores manifest icons, so the home-screen icon comes from this link.
  icons: {
    apple: [{ url: "/icons/apple-touch-icon-180.png", sizes: "180x180" }],
  },
  appleWebApp: {
    capable: true,
    title: WEB_APP_NAME,
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafbf8" },
    { media: "(prefers-color-scheme: dark)", color: "#172b26" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="antialiased h-full">
      <body className={`${spaceGrotesk.variable} ${inter.variable} min-h-full flex flex-col font-sans transition-colors duration-200`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          storageKey={THEME_STORAGE_KEY}
          enableSystem
          disableTransitionOnChange
        >
          <I18nProvider>
            <AuthLinkErrorGate>{children}</AuthLinkErrorGate>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
