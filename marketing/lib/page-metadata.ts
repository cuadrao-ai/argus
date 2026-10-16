import type { BusinessLocale, BusinessPage } from "./site-routes";
import { touchupCopy } from "../components/touchup-copy";

type PageMetadata = { title: string; description: string };

export const PAGE_METADATA: Record<
  BusinessLocale,
  Record<BusinessPage, PageMetadata | null>
> = {
  es: {
    home: {
      title: "Cada cuenta. En su sitio. | Cuadrao",
      description: touchupCopy.es.description,
    },
    contact: {
      title: "Hablemos de tu negocio | Cuadrao",
      description:
        "Cuéntale a Lucas cómo llevas tu negocio y conoce lo que estamos preparando en Cuadrao.",
    },
    personal: {
      title: "Tus finanzas, en orden. | Cuadrao Personal",
      description:
        "Conoce Cuadrao Personal y deja tu correo para recibir noticias sobre el acceso anticipado.",
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
      description: touchupCopy.en.description,
    },
    contact: {
      title: "Let's talk about your business | Cuadrao",
      description:
        "Tell Lucas how you run your business and explore what we are preparing at Cuadrao.",
    },
    personal: {
      title: "Your finances, in order. | Cuadrao Personal",
      description:
        "Meet Cuadrao Personal and leave your email to hear about early access.",
    },
    terms: null,
    deletion: null,
    privacy: {
      title: "Privacy | Cuadrao",
      description:
        "What data Cuadrao receives when you write to us or sign up, what we use it for and how to ask us to delete it.",
    },
  },
};

type ShareImage = { url: string; width: number; height: number; alt: string };

export function shareImage(
  locale: BusinessLocale,
  page: BusinessPage,
): ShareImage {
  const personal = page === "personal";
  return {
    url: `/cuadrao-site/share-${personal ? "personal" : "business"}-${locale}.png`,
    width: 1200,
    height: 630,
    alt: personal
      ? locale === "es"
        ? "Cuadrao Personal. Tus finanzas, en orden."
        : "Cuadrao Personal. Your finances, in order."
      : locale === "es"
        ? "Cuadrao para negocios. Cada cuenta. En su sitio."
        : "Cuadrao Business. Every record. In its place.",
  };
}
