import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase-server";
import ChatInterface from "@/components/chat/ChatInterface";
import ConversationShellGuard from "@/components/chat/ConversationShellGuard";
import { DevModeBadge } from "@/components/ui/DevModeBadge";
import { businessPilotEnabled, guestAccessEnabled } from "@/lib/private-alpha-flags";
import { guestCaptchaConfigured } from "@/lib/guest-session";
import { resolveChatEntrySurface } from "@/lib/landing-entry";
import { authLoginPathFromSearch } from "@/lib/landing-intent";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const isMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  if (!isMockAuth) {
    const supabase = await createClient();
    const { data, error } = await supabase.auth.getUser();
    if (
      resolveChatEntrySurface({
        hasEstablishedUser: !error && Boolean(data.user),
        guestAccessEnabled,
        guestCaptchaConfigured,
        businessBuild: businessPilotEnabled,
      }) === "auth"
    ) {
      redirect(authLoginPathFromSearch(await searchParams, "/chat"));
    }
  }

  return (
    <main className="min-h-[100dvh] bg-background text-foreground selection:bg-black/10 dark:selection:bg-white/20">
      <DevModeBadge />
      <ConversationShellGuard />
      <ChatInterface />
    </main>
  );
}
