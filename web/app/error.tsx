"use client";

import { useState } from "react";

import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { referenceCode } from "@/lib/failure-screen";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [reference] = useState(() => referenceCode(error));
  return <ServerErrorScreen onRetry={reset} reference={reference} />;
}
