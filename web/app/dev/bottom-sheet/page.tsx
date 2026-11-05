import { notFound } from "next/navigation";
import BottomSheetPlaygroundClient from "./BottomSheetPlaygroundClient";

export const metadata = {
  title: "Bottom Sheet Playground - Cuadrao",
};

export const dynamic = "force-dynamic";

export default function BottomSheetPlaygroundPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <BottomSheetPlaygroundClient />;
}
