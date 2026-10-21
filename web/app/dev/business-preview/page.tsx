import { notFound } from "next/navigation";
import BusinessApp from "@/components/business-app/BusinessApp";
import { IgualarGate } from "@/components/business-app/transacciones/transacciones-gate";

export const metadata = { title: "Business preview (sample data) - Cuadrao" };
export const dynamic = "force-dynamic";

/** Business chat is off, as in the product by default; `?chat=on` serves a workspace with chat. `?accounts=none` serves one with no account yet. `?bank=on` turns on Transacciones' igualar parts for this preview, as `businessBankMatchingEnabled` would, over the sample bank; `?bank=api` does the same over the real bank routes. */
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
      {bank === "on" || bank === "api" ? <IgualarGate enabled transport={bank === "api" ? "api" : "sample"}>{app}</IgualarGate> : app}
    </main>
  );
}
