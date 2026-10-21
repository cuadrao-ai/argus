import { notFound } from "next/navigation";
import ResultCardPlaygroundClient from "./ResultCardPlaygroundClient";

export const metadata = {
  title: "Result Card Playground - Cuadrao",
};

export const dynamic = "force-dynamic";

export default function ResultCardPlaygroundPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <ResultCardPlaygroundClient />;
}
