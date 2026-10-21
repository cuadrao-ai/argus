import { notFound } from "next/navigation";

import ControlsPreview from "./ControlsPreview";

export const dynamic = "force-dynamic";

/** Dev only: the segmented control and the switch, to judge their motion by hand. */
export default function ControlsPreviewPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <ControlsPreview />;
}
