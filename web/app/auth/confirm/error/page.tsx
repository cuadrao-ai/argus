"use client";

import { useEffect, useState } from "react";

import { AuthLinkErrorScreen } from "@/components/status/AuthLinkErrorScreen";
import { confirmErrorView, type AuthLinkErrorView } from "@/lib/auth-link-error";

export default function ConfirmErrorPage() {
  const [view, setView] = useState<AuthLinkErrorView | null>(null);

  useEffect(() => {
    setView(confirmErrorView(window.location.search));
  }, []);

  if (!view) return null;
  return <AuthLinkErrorScreen view={view} />;
}
