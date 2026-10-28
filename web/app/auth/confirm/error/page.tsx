"use client";

import { useEffect, useState } from "react";

import { AuthLinkErrorScreen } from "@/components/status/AuthLinkErrorScreen";
import { confirmErrorView, confirmReference, type AuthLinkErrorView } from "@/lib/auth-link-error";
import { referenceCode } from "@/lib/failure-screen";

export default function ConfirmErrorPage() {
  const [shown, setShown] = useState<{ view: AuthLinkErrorView; reference: string } | null>(null);

  useEffect(() => {
    const search = window.location.search;
    setShown({ view: confirmErrorView(search), reference: confirmReference(search) ?? referenceCode(null) });
  }, []);

  if (!shown) return null;
  return <AuthLinkErrorScreen view={shown.view} reference={shown.reference} />;
}
