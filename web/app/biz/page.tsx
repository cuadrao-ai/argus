import { notFound, redirect } from "next/navigation";
import { createClient } from "@/lib/supabase-server";
import BusinessApp from "@/components/business-app/BusinessApp";
import { DevModeBadge } from "@/components/ui/DevModeBadge";
import { businessPilotEnabled } from "@/lib/private-alpha-flags";
import { authLoginPathFromSearch } from "@/lib/landing-intent";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function BusinessPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (!businessPilotEnabled) notFound();
  const search = await searchParams;
  const transferId = typeof search.transfer === "string" ? search.transfer : undefined;
  if (process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") {
    const supabase = await createClient();
    const { data, error } = await supabase.auth.getUser();
    // A guest session is an anonymous Supabase user; Business has no guest mode.
    if (error || !data.user || data.user.is_anonymous) {
      redirect(authLoginPathFromSearch(search, "/biz"));
    }
  }
  return (
    <main className="min-h-[100dvh] bg-background text-foreground selection:bg-black/10 dark:selection:bg-white/20">
      <DevModeBadge />
      <BusinessApp transferId={transferId} />
    </main>
  );
}
