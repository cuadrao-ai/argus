import { renderAccountEmail } from "./account-layout.generated";
import { z } from "zod";
import { renderResetPasswordEmail } from "./reset-password";
import { emailExpiry } from "./expiry";
import { DISABLED_SECURITY_NOTICES, renderSecurityMail, type SecurityMail } from "./security-notices";
import { authConfirmHref, confirmLinkNext } from "../../lib/auth-confirm";

const address = z.email().max(254);
const tokenHash = z.string().regex(/^(?:pkce_)?[a-f0-9]{32,128}$/);
const otp = z.string().regex(/^[0-9]{6,10}$/);
const payloadSchema = z.object({
  user: z.object({ email: address, new_email: address.optional() }),
  email_data: z.object({
    email_action_type: z.enum(["signup", "magiclink", "recovery", "invite", "email_change", "reauthentication", "password_changed_notification", "email_changed_notification", ...DISABLED_SECURITY_NOTICES]),
    site_url: z.string().max(2048),
    redirect_to: z.string().max(2048),
    token_hash: z.string().max(133).optional(),
    token_hash_new: z.string().max(133).optional(),
    token: z.string().max(10).optional(),
    token_new: z.string().max(10).optional(),
    old_email: z.string().max(254).optional(),
  }),
});

export type AuthMail =
  | { action: "signup"; recipient: string; tokenHash: string; redirectTo: string; token: string }
  | { action: "magiclink"; recipient: string; tokenHash: string; redirectTo: string; token: string }
  | { action: "recovery"; recipient: string; tokenHash: string; redirectTo: string }
  | { action: "invite"; recipient: string; tokenHash: string; redirectTo: string }
  | { action: "email_change"; audience: "old_address" | "new_address"; recipient: string; tokenHash: string; redirectTo: string; newEmail: string }
  | { action: "reauthentication"; recipient: string; token: string }
  | SecurityMail;

function sameOrigin(value: string, origin: string) {
  const url = new URL(value);
  if (url.origin !== origin || url.username || url.password || url.protocol !== "https:") throw new Error("Invalid Auth origin");
  return url;
}

export function parseAuthMail(value: unknown, appOrigin: string): AuthMail[] {
  const { user, email_data: data } = payloadSchema.parse(value);
  const site = sameOrigin(data.site_url, appOrigin);
  if (site.pathname !== "/" || site.search || site.hash) throw new Error("Invalid Auth site");
  if (data.redirect_to) sameOrigin(data.redirect_to, appOrigin);
  if (DISABLED_SECURITY_NOTICES.some(action => action === data.email_action_type)) return [];
  if (data.email_action_type === "password_changed_notification") return [{ action: data.email_action_type, recipient: user.email }];
  if (data.email_action_type === "email_changed_notification") {
    return [{ action: data.email_action_type, recipient: address.parse(data.old_email), newEmail: user.email }];
  }
  if (data.email_action_type === "reauthentication") {
    return [{ action: data.email_action_type, recipient: user.email, token: otp.parse(data.token) }];
  }
  const hash = tokenHash.parse(data.token_hash);
  if (data.email_action_type === "email_change") {
    const newEmail = address.parse(user.new_email);
    const currentHash = tokenHash.parse(data.token_hash_new);
    otp.parse(data.token);
    otp.parse(data.token_new);
    return [
      { action: "email_change", audience: "old_address", recipient: user.email, tokenHash: currentHash, redirectTo: data.redirect_to, newEmail },
      { action: "email_change", audience: "new_address", recipient: newEmail, tokenHash: hash, redirectTo: data.redirect_to, newEmail },
    ];
  }
  if (data.email_action_type === "recovery") {
    if (data.redirect_to && data.redirect_to !== `${appOrigin}/auth/recovery`) throw new Error("Invalid recovery redirect");
    return [{ action: data.email_action_type, recipient: user.email, tokenHash: hash, redirectTo: data.redirect_to }];
  }
  if (data.email_action_type === "signup" || data.email_action_type === "magiclink") {
    return [{ action: data.email_action_type, recipient: user.email, tokenHash: hash, redirectTo: data.redirect_to, token: otp.parse(data.token) }];
  }
  if (data.email_action_type === "invite") {
    return [{ action: data.email_action_type, recipient: user.email, tokenHash: hash, redirectTo: data.redirect_to }];
  }
  throw new Error("Unsupported Auth email");
}

function confirmUrl(mail: Extract<AuthMail, { action: "recovery" | "email_change" | "invite" }>, linkHost: string) {
  return authConfirmHref(
    linkHost,
    mail.tokenHash,
    mail.action,
    confirmLinkNext(mail.action, mail.redirectTo, linkHost),
  );
}

export async function renderAuthMail(mail: AuthMail, linkHost: string, expirySeconds: number, sentAt = new Date()) {
  if (mail.action === "password_changed_notification" || mail.action === "email_changed_notification") return renderSecurityMail(mail, sentAt);
  const expires = emailExpiry(expirySeconds);
  if (mail.action === "reauthentication") {
    return { subject: `${mail.token} es tu código de verificación de Cuadrao`, ...renderAccountEmail({
      title: "Tu código de verificación", preheader: `Úsalo para confirmar que eres tú. Vence en ${expires}.`,
      intro: ["Hola,", "Usa este código para confirmar que eres tú:"], paragraphs: [], code: mail.token,
      expiryNote: `El código vence en ${expires} y solo se puede usar una vez.`,
      afterAction: "Si no fuiste tú, no compartas este código y escríbenos.",
    }) };
  }
  if (mail.action === "signup" || mail.action === "magiclink") {
    const signup = mail.action === "signup";
    return { subject: `${mail.token} es tu código ${signup ? "de Cuadrao" : "para entrar a Cuadrao"}`, ...renderAccountEmail({
      title: signup ? "Tu código de Cuadrao" : "Tu código para entrar",
      preheader: signup
        ? `Escríbelo en Cuadrao para confirmar tu cuenta. Vence en ${expires}.`
        : `Escríbelo en Cuadrao para entrar. Vence en ${expires}.`,
      intro: ["Hola,", signup ? "Escribe este código en Cuadrao para confirmar tu cuenta:" : "Escribe este código en Cuadrao para entrar:"],
      paragraphs: [],
      code: mail.token,
      expiryNote: `El código vence en ${expires} y solo se puede usar una vez.`,
      afterAction: signup
        ? `Lo pediste para ${mail.recipient}. Si no fuiste tú, ignora este correo.`
        : `Lo pediste para ${mail.recipient}. Si no fuiste tú, ignora este correo. Nadie puede entrar sin este código.`,
    }) };
  }
  const url = confirmUrl(mail, linkHost);
  if (mail.action === "invite") {
    return { subject: "Te invitaron a Cuadrao", ...renderAccountEmail({
      title: "Te invitaron a Cuadrao",
      preheader: `Te invitaron a usar Cuadrao. El enlace vence en ${expires}.`,
      intro: ["Hola,"],
      paragraphs: ["Te invitaron a usar Cuadrao."],
      action: { label: "Acepta aquí", url },
      expiryNote: `El enlace vence en ${expires} y solo se puede usar una vez.`,
      afterAction: "Si no fuiste tú, ignora este correo.",
    }) };
  }
  if (mail.action === "recovery") return renderResetPasswordEmail(url, expirySeconds);
  const old = mail.audience === "old_address";
  return { subject: old ? "Cambio de correo en tu cuenta de Cuadrao" : "Confirma tu nuevo correo", ...renderAccountEmail({
    title: old ? "Cambio de correo en tu cuenta" : "Confirma tu nuevo correo",
    preheader: old ? `Recibimos una solicitud para cambiar tu correo a ${mail.newEmail}.` : `Confirma que quieres usar este correo en Cuadrao. Vence en ${expires}.`,
    intro: ["Hola,"], paragraphs: old ? [
      `Recibimos una solicitud para cambiar el correo de tu cuenta de Cuadrao a ${mail.newEmail}.`,
      "Si fuiste tú, confirma el cambio desde este enlace:",
    ] : ["Recibimos una solicitud para usar este correo en tu cuenta de Cuadrao. Para confirmarlo, usa este enlace:"],
    action: { label: old ? "Confirmar el cambio" : "Confirmar mi correo", url },
    expiryNote: `El enlace vence en ${expires} y solo se puede usar una vez.`,
    afterAction: old ? "Si no fuiste tú, no confirmes el cambio y escríbenos." : "Si no fuiste tú, ignora este correo.",
  }) };
}
