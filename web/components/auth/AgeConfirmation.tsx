"use client";

import { useState } from "react";
import { confirmAge } from "@/lib/age-confirmation";
import { useAgeConfirmation } from "@/lib/use-age-confirmation";

export default function AgeConfirmation() {
  const confirmedAt = useAgeConfirmation();
  const [acceptedHere, setAcceptedHere] = useState(false);
  if (confirmedAt && !acceptedHere) return null;
  return (
    <label className="my-3 flex items-start gap-3 px-1 text-sm text-black/70 dark:text-white/70">
      <input type="checkbox" required checked={Boolean(confirmedAt)} disabled={Boolean(confirmedAt)} className="mt-0.5 h-5 w-5 shrink-0 accent-black dark:accent-white"
        onChange={(event) => { if (event.target.checked) { setAcceptedHere(true); confirmAge(); } }} />
      <span>Confirmo que tengo 18 años o más.</span>
    </label>
  );
}
