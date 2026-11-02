import type { BusinessLocale, BusinessPage } from "./site-routes";
import { landingCopy } from "../components/landing/landing-copy";

type PageMetadata = { title: string; description: string };

export const PAGE_METADATA: Record<
  BusinessLocale,
  Record<BusinessPage, PageMetadata | null>
> = {
  es: {
    home: {
      title: "Cada cuenta. En su sitio. | Cuadrao",
      description: landingCopy.es.lead,
    },
    contact: {
      title: "Hablemos de tu negocio | Cuadrao",
      description:
        "Cuéntale a Lucas cómo llevas tu negocio y conoce lo que estamos preparando en Cuadrao.",
    },
    terms: { title: "Términos | Cuadrao", description: "Términos de uso del sitio web de Cuadrao." },
    deletion: { title: "Eliminar tus datos | Cuadrao", description: "Cómo pedir que borremos tus datos en Cuadrao." },
    privacy: {
      title: "Privacidad | Cuadrao",
      description:
        "Qué datos recibe Cuadrao cuando escribes o te registras, para qué los usamos y cómo pedir que los eliminemos.",
    },
  },
  en: {
    home: {
      title: "Every record. In its place. | Cuadrao",
      description: landingCopy.en.lead,
    },
    contact: {
      title: "Let’s talk about your business | Cuadrao",
      description:
        "Tell Lucas how you run your business and explore what we are preparing at Cuadrao.",
    },
    terms: { title: "Terms | Cuadrao", description: "Cuadrao Website Terms of Use" },
    deletion: { title: "Delete your data | Cuadrao", description: "How to ask us to delete your data" },
    privacy: {
      title: "Privacy | Cuadrao",
      description:
        "What data Cuadrao receives when you write to us or sign up, what we use it for and how to ask us to delete it.",
    },
  },
};

type ShareImage = { url: string; width: number; height: number; alt: string };

export function shareImage(locale: BusinessLocale): ShareImage {
  return {
    url: `/cuadrao-site/share-business-${locale}.png`,
    width: 1200,
    height: 630,
    alt: locale === "es"
      ? "Cuadrao para negocios. Cada cuenta. En su sitio."
      : "Cuadrao Business. Every record. In its place.",
  };
}
