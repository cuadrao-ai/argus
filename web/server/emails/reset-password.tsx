import { renderAccountEmail } from "./account-layout.generated";

export async function renderResetPasswordEmail(recoveryUrl: string) {
  return { subject: "Cambia tu contraseña de Cuadrao", ...renderAccountEmail({
    title: "Cambia tu contraseña de Cuadrao",
    paragraphs: ["Pediste cambiar tu contraseña."],
    action: { label: "Hazlo aquí", url: recoveryUrl },
    expiryNote: "El enlace vence en 1 hora y solo se puede usar una vez.",
    afterAction: "Si no fuiste tú, ignora este correo. Tu contraseña sigue igual.",
  }) };
}
