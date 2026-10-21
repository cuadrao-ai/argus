import { notFound } from "next/navigation";
import BusinessApp from "@/components/business-app/BusinessApp";

export const metadata = { title: "Business preview (sample data) - Cuadrao" };
export const dynamic = "force-dynamic";

/** `?chat=off` serves a workspace whose Business chat is not available; `?accounts=none` one with no account yet. */
export default async function BusinessPreviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const { chat, accounts } = await searchParams;
  return (
    <main className="min-h-[100dvh] bg-background text-foreground">
      <BusinessApp sample={{ chatAvailable: chat !== "off", accounts: accounts === "none" ? "none" : undefined }} />
    </main>
  );
}
