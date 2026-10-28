"use client";

import { AuthLinkErrorScreen } from "@/components/status/AuthLinkErrorScreen";
import { NotFoundScreen } from "@/components/status/NotFoundScreen";
import type { AuthLinkErrorView } from "@/lib/auth-link-error";

export function AuthLinkErrorClient({ view, reference }: { view: AuthLinkErrorView | null; reference: string }) {
  if (!view) return <NotFoundScreen />;
  return <AuthLinkErrorScreen view={view} reference={reference} />;
}
