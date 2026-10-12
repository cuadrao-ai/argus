import { businessContactEmail } from "./site-copy";
import type { BusinessLocale } from "@/lib/site-routes";

type Section = { id: string; title: string; paragraphs?: string[]; items?: string[] };

type PrivacyCopy = {
  eyebrow: string;
  title: string;
  intro: string;
  updated: string;
  sections: Section[];
};

const email = businessContactEmail;

const es: PrivacyCopy = {
  eyebrow: "PRIVACIDAD",
  title: "Tu privacidad en Cuadrao.",
  intro:
    "Usamos los datos que compartes para responder tus consultas y avisarte cuando esté disponible el acceso anticipado. Aquí explicamos qué información recibimos, cómo la usamos y cómo puedes solicitar su eliminación.",
  updated: "Actualizado el 8 de octubre de 2026",
  sections: [
    {
      id: "data",
      title: "Qué datos recibimos",
      paragraphs: [
        "Si nos escribes: tu nombre, tu correo, el comentario opcional, el idioma de la página y, si lo compartes, tu número de WhatsApp. Los usamos para responderte.",
        "Si pides acceso anticipado a Cuadrao Personal: tu correo, el idioma de la página, la fecha del registro y la versión de este texto que aceptaste. Los usamos solo para avisarte cuando haya acceso disponible. Registrarte no crea una cuenta ni garantiza acceso inmediato.",
        "Cuando visitas el sitio: el proveedor de alojamiento puede registrar datos técnicos de la conexión, como la dirección IP.",
        "Para frenar envíos automáticos, el sitio guarda tu dirección IP y, si nos escribes, tu correo en la memoria del servidor, no en una base de datos. Se olvidan en un máximo de dos horas, o antes si el servicio se reinicia.",
      ],
    },
    {
      id: "not-used",
      title: "Qué no usamos",
      paragraphs: [
        "Este sitio no usa cookies, herramientas de analítica ni seguimiento publicitario, y no guarda datos en tu navegador. Las tipografías se sirven desde el mismo sitio. No usamos tus datos de contacto para enviarte publicidad.",
        "Te pedimos que no escribas documentos, números de cuenta ni información financiera privada en el formulario.",
      ],
    },
    {
      id: "providers",
      title: "Proveedores que intervienen",
      items: [
        "Render aloja el sitio.",
        "Resend envía por correo los mensajes del formulario y, más adelante, el aviso de acceso anticipado. Puede conservar sus propios registros de envío.",
        `Apple (iCloud Mail) recibe y guarda los correos que llegan a ${email}, incluidos los mensajes del formulario y las solicitudes de retiro.`,
        "Supabase guarda los registros de acceso anticipado en servidores de Estados Unidos (Ohio).",
        "Cloudflare administra el dominio cuadrao.ai.",
      ],
    },
    {
      id: "retention",
      title: "Cuánto tiempo los conservamos",
      paragraphs: [
        "Tu mensaje se conserva en nuestro correo mientras haga falta para responderte y dar seguimiento a la conversación.",
        "Tu registro de acceso anticipado permanece hasta que pidas retirarlo. Al retirarlo borramos tu correo y conservamos una huella técnica de la dirección, sin la dirección misma, junto con el idioma y las fechas del registro, del aviso y del retiro, para no volver a registrarte ni escribirte.",
        "Los registros técnicos de la conexión los conserva el proveedor de alojamiento según sus propias reglas.",
      ],
    },
    {
      id: "choices",
      title: "Tus opciones y contacto",
      paragraphs: [
        `Puedes pedirnos ver, corregir o eliminar tus datos, o retirar tu registro, escribiendo a ${email}. Atendemos esas solicitudes manualmente.`,
      ],
    },
  ],
};

const en: PrivacyCopy = {
  eyebrow: "PRIVACY",
  title: "Your privacy at Cuadrao.",
  intro:
    "We use the data you share to answer your inquiries and to tell you when early access is available. This page explains what information we receive, how we use it and how you can ask us to delete it.",
  updated: "Updated October 8, 2026",
  sections: [
    {
      id: "data",
      title: "What data we receive",
      paragraphs: [
        "If you write to us: your name, your email, the optional comment, the page language and, if you share it, your WhatsApp number. We use them to reply to you.",
        "If you request Cuadrao Personal early access: your email, the page language, the signup date and the version of this text you accepted. We use them only to tell you when access is available. Signing up does not create an account or guarantee immediate access.",
        "When you visit the site: the hosting provider may record technical connection data, such as the IP address.",
        "To slow down automated submissions, the site keeps your IP address and, if you write to us, your email in the server's memory, not in a database. They are forgotten after at most two hours, or sooner if the service restarts.",
      ],
    },
    {
      id: "not-used",
      title: "What we do not use",
      paragraphs: [
        "This site does not use cookies, analytics tools or advertising tracking, and it does not store data in your browser. Fonts are served from the site itself. We do not use your contact details to send you advertising.",
        "Please do not enter documents, account numbers or private financial information in the form.",
      ],
    },
    {
      id: "providers",
      title: "Providers involved",
      items: [
        "Render hosts the site.",
        "Resend sends the form messages by email and, later, the early-access notice. It may keep its own sending logs.",
        `Apple (iCloud Mail) receives and stores the email sent to ${email}, including form messages and removal requests.`,
        "Supabase stores early-access signups on servers in the United States (Ohio).",
        "Cloudflare manages the cuadrao.ai domain.",
      ],
    },
    {
      id: "retention",
      title: "How long we keep it",
      paragraphs: [
        "Your message is kept in our email for as long as it is needed to reply and follow up.",
        "Your early-access signup stays until you ask to remove it. When you remove it we delete your email and keep a technical fingerprint of the address, not the address itself, along with the language and the signup, notice and removal dates, so we do not register or email you again.",
        "Technical connection records are kept by the hosting provider under its own rules.",
      ],
    },
    {
      id: "choices",
      title: "Your choices and contact",
      paragraphs: [
        `You can ask us to show, correct or delete your data, or to remove your signup, by writing to ${email}. We handle these requests by hand.`,
      ],
    },
  ],
};

export const privacyCopy: Record<BusinessLocale, PrivacyCopy> = { es, en };
