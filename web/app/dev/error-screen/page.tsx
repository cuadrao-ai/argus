import { notFound } from "next/navigation";

import ErrorScreenPreview from "./ErrorScreenPreview";

export const dynamic = "force-dynamic";

export default async function ErrorScreenPreviewPage({
  searchParams,
}: {
  searchParams: Promise<{ screen?: string }>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const params = await searchParams;
  return <ErrorScreenPreview screen={params.screen ?? "server"} />;
}
