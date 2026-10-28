"use client";

import { useLayoutEffect, useState, type ReactNode } from "react";

import { AuthLinkErrorScreen } from "@/components/status/AuthLinkErrorScreen";
import { mapAuthLinkError, rendersOwnLinkError, type AuthLinkErrorView } from "@/lib/auth-link-error";
import { referenceCode } from "@/lib/failure-screen";

export function AuthLinkErrorGate({ children }: { children: ReactNode }) {
  const [shown, setShown] = useState<{ view: AuthLinkErrorView; reference: string } | null>(null);

  useLayoutEffect(() => {
    if (rendersOwnLinkError(window.location.pathname)) return;
    const view = mapAuthLinkError({
      search: window.location.search,
      hash: window.location.hash,
      pathname: window.location.pathname,
    });
    if (view) setShown({ view, reference: referenceCode(null) });
  }, []);

  if (shown) return <AuthLinkErrorScreen view={shown.view} reference={shown.reference} />;
  return children;
}
