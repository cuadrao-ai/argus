import { redirect } from "next/navigation";

import { cuadraoLegalLinks } from "@/lib/cuadrao-legal-links";

export default function PrivacyPage(): never {
  redirect(cuadraoLegalLinks().privacy);
}
