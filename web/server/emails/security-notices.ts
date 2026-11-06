import spanish from "../../public/locales/es-419/common.json";
import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout.generated";

export const DISABLED_SECURITY_NOTICES = [
  "phone_changed_notification", "identity_linked_notification", "identity_unlinked_notification",
  "mfa_factor_enrolled_notification", "mfa_factor_unenrolled_notification",
] as const;

export type SecurityMail =
  | { action: "password_changed_notification"; recipient: string }
  | { action: "email_changed_notification"; recipient: string; newEmail: string };

export function renderSecurityMail(mail: SecurityMail, _sentAt: Date, options: EmailLayoutOptions = {}) {
  const copy = spanish.account_email.auth_security;
  const shared = copy.safety_warning;
  if (mail.action === "password_changed_notification") {
    return { subject: "Tu contraseña de Cuadrao cambió", ...renderAccountEmail({
      signOff: false,
      title: "Tu contraseña cambió", preheader: "Si hiciste este cambio, no tienes que hacer nada.",
      intro: [], paragraphs: [
        copy.password_changed_description,
        "Si fuiste tú, no tienes que hacer nada.",
        'Si no fuiste tú, abre Cuadrao, toca "¿Olvidaste tu contraseña?" en la pantalla para entrar y crea una nueva. Luego escríbenos de inmediato.', shared,
      ],
    }, options) };
  }
  const addresses = { oldEmail: mail.recipient, newEmail: mail.newEmail };
  return { subject: "El correo de tu cuenta de Cuadrao cambió", ...renderAccountEmail({
    signOff: false,
    title: "Tu correo cambió", preheader: "Te avisamos aquí porque era el correo de tu cuenta.",
    intro: [], paragraphs: [
      copy.email_changed_description.replace(/\{\{(oldEmail|newEmail)\}\}/g, (_match, key: keyof typeof addresses) => addresses[key]),
      "Te avisamos a esta dirección porque era la de tu cuenta. Desde ahora, los avisos llegarán a la dirección nueva.",
      "Si fuiste tú, no tienes que hacer nada.",
      copy.recovery_contact, shared,
    ],
  }, options) };
}
