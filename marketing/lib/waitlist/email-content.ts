const confirmationText = "Recibimos tu solicitud para la lista de espera de la app personal de Cuadrao, para llevar tus gastos y los de tu hogar. Confirma tu correo para que te avisemos cuando esté lista para ti.";

export const WAITLIST_BUSINESS_LINE = "¿Buscas Cuadrao para tu negocio? Es un servicio aparte. Escríbenos en cuadrao.ai/contacto.";

export const WAITLIST_EMAILS = {
  confirmation: {
    subject: "Confirma tu lugar en la lista de la app personal de Cuadrao",
    paragraphs: [confirmationText],
    button: "Confirmar mi correo",
    expiryNote: "Este enlace vence en 48 horas.",
    afterAction: "Si no te anotaste, ignora este correo.",
    automatic: true,
  },
  reminder: {
    subject: "¿Sigues interesado? Confirma tu lugar en Cuadrao",
    paragraphs: [confirmationText],
    button: "Confirmar mi correo",
    expiryNote: "Este enlace vence en 48 horas.",
    afterAction: "Si no te anotaste, ignora este correo.",
    automatic: true,
  },
  welcome: {
    subject: "Ya estás en la lista de la app personal de Cuadrao",
    paragraphs: ["Gracias por anotarte. Estamos construyendo Cuadrao para ti y te escribiremos cuando esté listo. Si quieres contarnos qué esperas de la app, responde este correo. Leemos cada respuesta."],
    automatic: true,
  },
  launch: {
    subject: "La app personal de Cuadrao",
    paragraphs: [],
    automatic: false,
  },
} as const;

export type AutomaticWaitlistEmail = Exclude<keyof typeof WAITLIST_EMAILS, "launch">;

export function unsubscribeHeaders(url: string): Record<string, string> {
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || /[\r\n<>]/.test(url)) throw new Error("Invalid unsubscribe URL");
  return {
    "List-Unsubscribe": `<${url}>`,
    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
  };
}
