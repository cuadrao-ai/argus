import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout";

export type BusinessClosedEmailData = {
  businessName: string;
  ownerName: string;
  closedDate: string;
  purgeDate: string;
};

export function renderBusinessClosedEmail(data: BusinessClosedEmailData, options: EmailLayoutOptions = {}) {
  if (Object.values(data).some(value => !value.trim() || /[\r\n]/.test(value))) {
    throw new Error("Business close email fields must be nonempty single-line values");
  }
  const subject = `${data.businessName} se cerró en Cuadrao`;
  const body = `Hola, ${data.ownerName} cerró ${data.businessName} en Cuadrao el ${data.closedDate}, y ya no tienes acceso. Si necesitas copias de los comprobantes, pídeselas a ${data.ownerName}. Si el negocio no se reabre antes del ${data.purgeDate}, sus datos se borrarán. Saludos, Cuadrao`;
  return { subject, ...renderAccountEmail({ title: subject, paragraphs: [body] }, options) };
}
