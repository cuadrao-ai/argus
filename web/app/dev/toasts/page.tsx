import { notFound } from "next/navigation";

import ToastPreview from "./ToastPreview";

export const dynamic = "force-dynamic";

/** Dev only: every toast kind on the real presenter, to judge position, timing, stacking and dismissal. */
export default function ToastPreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <ToastPreview />;
}
