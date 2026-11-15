"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { SessionRecoveryScreen } from "@/components/status/SessionRecoveryScreen";

export function BusinessEntryRecovery() {
  const router = useRouter();
  const [busy, startTransition] = useTransition();

  return <SessionRecoveryScreen state="error" busy={busy} onRetry={() => startTransition(() => router.refresh())} />;
}
