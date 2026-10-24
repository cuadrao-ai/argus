import { notFound } from "next/navigation";
import Preview from "./preview";

export default function Page() {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") notFound();
  return <Preview />;
}
