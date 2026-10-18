import { renderAccountEmail } from "./account-layout.generated";
import { emailExpiry } from "./expiry";

export async function renderResetPasswordEmail(recoveryUrl: string, expirySeconds: number) {
  const expires = emailExpiry(expirySeconds);
  return { subject: "Cambio de contraseña en Cuadrao", ...renderAccountEmail({
    title: "Cambio de contraseña en Cuadrao",
    preheader: `Usa el enlace para crear una contraseña nueva. Vence en ${expires}.`,
    intro: ["Hola,"],
    paragraphs: ["Recibimos una solicitud para cambiar tu contraseña de Cuadrao. Puedes hacerlo desde este enlace:"],
    action: { label: "Cambiar mi contraseña", url: recoveryUrl },
    expiryNote: `El enlace vence en ${expires} y solo se puede usar una vez.`,
    afterAction: "Si no fuiste tú, ignora este correo. Tu contraseña sigue igual.",
  }) };
}
