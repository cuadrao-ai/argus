"use client";

import { useMemo, useSyncExternalStore } from "react";
import { CAMPAIGN_DAY, demoDates, demoDayKey, localDayKey, type DemoDates } from "@/lib/demo-date";
import type { LandingLocale } from "./landing-copy";

const subscribeToNothing = () => () => {};
const visitorDay = () => demoDayKey(localDayKey(new Date()));
const campaignDay = () => CAMPAIGN_DAY;

export function useDemoDates(locale: LandingLocale): DemoDates {
  const dayKey = useSyncExternalStore(subscribeToNothing, visitorDay, campaignDay);
  return useMemo(() => demoDates(dayKey, locale), [dayKey, locale]);
}
