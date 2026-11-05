"use client";

import { useEffect } from "react";

import { captureLandingIntentFromLocation } from "@/lib/landing-intent";

/** Capture campaign fields on public receipt landings, including /r/<id>. */
export default function LandingIntentCapture() {
  useEffect(() => {
    captureLandingIntentFromLocation();
  }, []);
  return null;
}
