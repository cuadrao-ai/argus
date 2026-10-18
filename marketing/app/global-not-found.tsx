import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import styles from "./not-found.module.css";

export const metadata: Metadata = {
  title: "Página no encontrada | Cuadrao",
  robots: { index: false },
};

// Rendered for every URL no page owns, in both languages: there is no locale
// to read from an unknown path.
export default function GlobalNotFound() {
  return (
    <html lang="es-DO" data-page-background="not-found">
      <body className={styles.page}>
        <main className={styles.card}>
          <span className={styles.mark} aria-hidden="true">c</span>
          <h1>Esta página no existe.</h1>
          <p>
            <Link href="/">Ir al inicio</Link>
          </p>
          <h2 lang="en">This page does not exist.</h2>
          <p lang="en">
            <Link href="/en">Go to the home page</Link>
          </p>
        </main>
      </body>
    </html>
  );
}
