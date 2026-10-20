"use client";

import { useEffect, useState } from "react";

import { getMe } from "@/lib/argus-api";
import { notFoundHref, prefilledEmail } from "@/lib/auth-link-error";
import { signedInHomePath } from "@/lib/landing-intent";

export function useSessionEntry(): { homeHref: string; email: string } {
  const [homeHref, setHomeHref] = useState(notFoundHref(false, "/chat"));
  const [email, setEmail] = useState("");

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => {
        if (cancelled || !me?.user) return;
        setHomeHref(notFoundHref(true, signedInHomePath()));
        setEmail(prefilledEmail(me.user.email));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return { homeHref, email };
}
