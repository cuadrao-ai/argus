"use client";

import { useEffect, useState } from "react";
import { businessReceivingAddress } from "@/lib/business-email";
import type { BusinessDataSource } from "./business-data";
import { useReceivingChannels } from "./business-context";
import { useBusiness } from "./BusinessWorkspace";

/** The Business's receipt forwarding address, or null while unknown or when email intake is off. */
export function useForwardAddress(): string | null {
  const { source, revision } = useBusiness();
  const channels = useReceivingChannels();
  return useSourceForwardAddress(channels.email.available ? source : null, revision);
}

/** The same address for a caller above the Business context; a null source reads nothing. */
export function useSourceForwardAddress(source: BusinessDataSource | null, revision = 0): string | null {
  const [loaded, setLoaded] = useState<{ source: BusinessDataSource; revision: number; address: string | null } | null>(null);
  useEffect(() => {
    if (!source?.emailIntake) { setLoaded(null); return undefined; }
    let live = true;
    source.emailIntake().then((intake) => {
      if (live) setLoaded({ source, revision, address: businessReceivingAddress(intake) });
    }).catch(() => {
      if (live) setLoaded(null);
    });
    return () => {
      live = false;
    };
  }, [source, revision]);
  return source && loaded?.source === source && loaded.revision === revision ? loaded.address : null;
}
