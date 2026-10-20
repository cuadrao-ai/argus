import { renderAccountEmail } from "./account-layout.generated";

export const DISABLED_SECURITY_NOTICES = [
  "phone_changed_notification", "identity_linked_notification", "identity_unlinked_notification",
  "mfa_factor_enrolled_notification", "mfa_factor_unenrolled_notification",
] as const;

export type SecurityMail =
  | { action: "password_changed_notification"; recipient: string }
  | { action: "email_changed_notification"; recipient: string; newEmail: string };

export function renderSecurityMail(mail: SecurityMail, sentAt: Date) {
  const date = new Intl.DateTimeFormat("es-DO", { timeZone: "America/Santo_Domingo", day: "numeric", month: "long", year: "numeric" }).format(sentAt);
  const time = new Intl.DateTimeFormat("es-DO", { timeZone: "America/Santo_Domingo", hour: "numeric", minute: "2-digit", hour12: true }).format(sentAt).replace(/[\u00a0\u202f]/g, " ");
  const when = `el ${date} a las ${time} (hora de RD).`;
  const shared = "Cuadrao nunca te pedirá tu contraseña ni tus códigos.";
  if (mail.action === "password_changed_notification") {
    return { subject: "Tu contraseña de Cuadrao cambió", ...renderAccountEmail({
      title: "Tu contraseña cambió", preheader: "Si hiciste este cambio, no tienes que hacer nada.",
      intro: ["Hola,"], paragraphs: [
        `La contraseña de tu cuenta de Cuadrao se cambió ${when}`,
        "Si fuiste tú, no tienes que hacer nada.",
        'Si no fuiste tú, abre Cuadrao, toca "¿Olvidaste tu contraseña?" en la pantalla para entrar y crea una nueva. Luego escríbenos de inmediato.', shared,
      ],
    }) };
  }
  const [local, domain] = mail.newEmail.split("@");
  const masked = `${local[0]}***@${domain}`;
  return { subject: "El correo de tu cuenta de Cuadrao cambió", ...renderAccountEmail({
    title: "Tu correo cambió", preheader: "Te avisamos aquí porque era el correo de tu cuenta.",
    intro: ["Hola,"], paragraphs: [
      `El correo de tu cuenta de Cuadrao cambió de ${mail.recipient} a ${masked} ${when}`,
      "Te avisamos a esta dirección porque era la de tu cuenta. Desde ahora, los avisos llegarán a la dirección nueva.",
      "Si fuiste tú, no tienes que hacer nada.",
      "Si no fuiste tú, escríbenos de inmediato respondiendo a este correo para recuperar tu cuenta.", shared,
    ],
  }) };
}
