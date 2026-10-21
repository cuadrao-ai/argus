import { notFound } from "next/navigation";
import BusinessApp from "@/components/business-app/BusinessApp";
import { TransaccionesGate } from "@/components/business-app/transacciones/transacciones-gate";

export const metadata = { title: "Business preview (sample data) - Cuadrao" };
export const dynamic = "force-dynamic";

/** Business chat is off, as in the product by default; `?chat=on` serves a workspace with chat. `?accounts=none` serves one with no account yet. `?bank=on` turns on Transacciones for this preview, as `businessBankMatchingEnabled` would. */
export default async function BusinessPreviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const { chat, accounts, bank } = await searchParams;
  const app = <BusinessApp sample={{ chatAvailable: chat === "on", accounts: accounts === "none" ? "none" : undefined }} />;
  return (
    <main className="min-h-[100dvh] bg-background text-foreground">
      {bank === "on" ? <TransaccionesGate enabled>{app}</TransaccionesGate> : app}
    </main>
  );
}
