"use client";

import ReceptionPreview from "./recepcion/ReceptionPreview";

/**
 * The one place arrivals wait: receipts, typed notes and emails as Recepción
 * lists them. Only the development preview over sample data keeps its local,
 * labeled stand-ins; every other build reads the server and shows no state it
 * cannot keep.
 */
export default function BusinessInboxPanel() {
  const preview = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  return <ReceptionPreview live={!preview} />;
}
