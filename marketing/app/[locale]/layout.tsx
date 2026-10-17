import "../globals.css";
import { notFound } from "next/navigation";
import localFont from "next/font/local";
import { LOCALES, htmlLang, isLocale } from "@/lib/site-routes";

const inter = localFont({
  src: "../fonts/InterVariable.woff2",
  variable: "--font-inter",
  weight: "100 900",
});

const spaceGrotesk = localFont({
  src: "../fonts/SpaceGrotesk[wght].woff2",
  variable: "--font-space-grotesk",
  weight: "300 700",
});

export const dynamicParams = false;

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function RootLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return (
    <html lang={htmlLang(locale)} className="antialiased h-full">
      <body
        className={`${spaceGrotesk.variable} ${inter.variable} min-h-full flex flex-col font-sans`}
      >
        {children}
      </body>
    </html>
  );
}
