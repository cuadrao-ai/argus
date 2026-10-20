import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout";

export type BusinessInviteEmailData = {
  ownerName: string;
  businessName: string;
  expiresDate: string;
  signInUrl: string;
};

export function renderBusinessInviteEmail(data: BusinessInviteEmailData, options: EmailLayoutOptions = {}) {
  if (Object.values(data).some(value => !value.trim() || /[\r\n]/.test(value))) {
    throw new Error("Business invite email fields must be nonempty single-line values");
  }
  const url = new URL(data.signInUrl);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("Business invitation must open ordinary sign-in without a token");
  }
  const subject = `${data.ownerName} te invitó a ${data.businessName} en Cuadrao`;
  return { subject, ...renderAccountEmail({
    title: subject,
    preheader: `Entra con este correo para aceptar. Vence el ${data.expiresDate}.`,
    paragraphs: [
      "Hola,",
      `${data.ownerName} te invitó a ${data.businessName} en Cuadrao para que puedas editar sus registros. Para aceptar, entra o crea tu cuenta con este correo.`,
      `La invitación vence el ${data.expiresDate}.`,
      `Si no conoces a ${data.ownerName}, ignora este correo.`,
    ],
    action: { label: "Aceptar invitación", url: data.signInUrl },
  }, options) };
}
