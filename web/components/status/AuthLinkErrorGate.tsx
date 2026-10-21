"use client";

import { useLayoutEffect, useState, type ReactNode } from "react";

import { AuthLinkErrorScreen } from "@/components/status/AuthLinkErrorScreen";
import { mapAuthLinkError, type AuthLinkErrorView } from "@/lib/auth-link-error";

export function AuthLinkErrorGate({ children }: { children: ReactNode }) {
  const [view, setView] = useState<AuthLinkErrorView | null>(null);

  useLayoutEffect(() => {
    if (window.location.pathname === "/auth/link-error") return;
    const mapped = mapAuthLinkError({
      search: window.location.search,
      hash: window.location.hash,
      pathname: window.location.pathname,
    });
    if (mapped) setView(mapped);
  }, []);

  if (view) return <AuthLinkErrorScreen view={view} />;
  return children;
}
