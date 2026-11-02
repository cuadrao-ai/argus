import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout";

export type TransferEmailVariant = "requested" | "declined" | "acceptedOwner" | "acceptedTarget" | "withdrawn";
export type TransferEmailData = {
  businessName: string;
  ownerName: string;
  targetName: string;
  eventDate: string;
  eventTime: string;
  expiresDate: string;
  transferUrl: string;
  businessUrl: string;
};

export function renderBusinessTransferEmail(variant: TransferEmailVariant, data: TransferEmailData, options: EmailLayoutOptions = {}) {
  if (Object.values(data).some(value => !value.trim() || /[\r\n]/.test(value))) throw new Error("Transfer email fields must be nonempty single-line values");
  const { businessName: business, ownerName: owner, targetName: target } = data;
  const content = {
    requested: {
      subject: `${owner} quiere transferirte ${business}`,
      title: `Transferencia de ${business}`,
      preheader: `Si aceptas, serás el dueño de ${business} en Cuadrao.`,
      paragraphs: ["Hola,", `${owner} quiere transferirte ${business} en Cuadrao. Si aceptas, serás su dueño y ${owner} podrá seguir editando.`, "Para aceptar o rechazar, entra a Cuadrao:"],
      action: { label: "Ver transferencia", url: data.transferUrl },
      expiryNote: `La solicitud vence el ${data.expiresDate}.`,
      afterAction: "Si no esperabas esto, puedes rechazarla desde la aplicación.",
    },
    declined: {
      subject: `${target} rechazó la transferencia de ${business}`,
      title: "Transferencia rechazada",
      preheader: `${business} sigue siendo tuyo.`,
      paragraphs: ["Hola,", `${target} rechazó la transferencia. ${business} sigue siendo tuyo.`, "Si quieres, puedes solicitar la transferencia a otro miembro desde Cuadrao."],
    },
    acceptedOwner: {
      subject: `${business} ahora es de ${target}`,
      title: "Transferencia completada",
      preheader: `${target} aceptó la transferencia de ${business}.`,
      paragraphs: ["Hola,", `${target} aceptó la transferencia. Desde el ${data.eventDate} a las ${data.eventTime} (hora de RD), ${target} es el dueño de ${business} en Cuadrao. Tú puedes seguir editando.`, "Si no fuiste tú quien pidió esta transferencia, escríbenos."],
    },
    acceptedTarget: {
      subject: `Ahora eres el dueño de ${business}`,
      title: "Transferencia completada",
      preheader: `Ya puedes administrar ${business} en Cuadrao.`,
      paragraphs: ["Hola,", `Aceptaste la transferencia. Desde el ${data.eventDate} a las ${data.eventTime} (hora de RD), eres el dueño de ${business} en Cuadrao, y ${owner} puede seguir editando.`],
      action: { label: `Abrir ${business}`, url: data.businessUrl },
    },
    withdrawn: {
      subject: `${owner} retiró la transferencia de ${business}`,
      title: "Transferencia retirada",
      preheader: "Ya no tienes una transferencia pendiente.",
      paragraphs: ["Hola,", `${owner} retiró la solicitud para transferirte ${business}. No tienes que hacer nada.`],
    },
  }[variant];
  return { subject: content.subject, ...renderAccountEmail(content, options) };
}
