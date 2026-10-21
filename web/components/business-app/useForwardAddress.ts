"use client";

import { useEffect, useState } from "react";
import { businessReceivingAddress } from "@/lib/business-email";
import type { BusinessDataSource } from "./business-data";
import { useBusiness } from "./BusinessWorkspace";

/** The Business's receipt forwarding address, or null while unknown or when email intake is off. */
export function useForwardAddress(): string | null {
  return useSourceForwardAddress(useBusiness().source);
}

/** The same address for a caller above the Business context; a null source reads nothing. */
export function useSourceForwardAddress(source: BusinessDataSource | null): string | null {
  const [address, setAddress] = useState<string | null>(null);
  useEffect(() => {
    if (!source?.emailIntake) return undefined;
    let live = true;
    source.emailIntake().then((intake) => {
      if (live) setAddress(businessReceivingAddress(intake));
    }).catch(() => {
      if (live) setAddress(null);
    });
    return () => {
      live = false;
    };
  }, [source]);
  return address;
}
