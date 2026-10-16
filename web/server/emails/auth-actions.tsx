import { renderAccountEmail } from "./account-layout.generated";
import { z } from "zod";
import { renderResetPasswordEmail } from "./reset-password";

const address = z.email().max(254);
const tokenHash = z.string().regex(/^(?:pkce_)?[a-f0-9]{32,128}$/);
const otp = z.string().regex(/^[0-9]{6,10}$/);
const payloadSchema = z.object({
  user: z.object({ email: address, new_email: address.optional() }),
  email_data: z.object({
    email_action_type: z.enum(["signup", "invite", "magiclink", "recovery", "email_change", "reauthentication"]),
    site_url: z.string().max(2048),
    redirect_to: z.string().max(2048),
    token_hash: z.string().max(133).optional(),
    token_hash_new: z.string().max(133).optional(),
    token: z.string().max(10).optional(),
    token_new: z.string().max(10).optional(),
  }),
});

type LinkedAction = "invite" | "recovery";
export type AuthMail =
  | { action: "signup" | "magiclink"; recipient: string; tokenHash: string; redirectTo: string; token: string }
  | { action: LinkedAction; recipient: string; tokenHash: string; redirectTo: string }
  | { action: "email_change"; recipient: string; tokenHash: string; redirectTo: string; newEmail: string }
  | { action: "reauthentication"; recipient: string; token: string };

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
  if (data.email_action_type === "reauthentication") {
    return [{ action: "reauthentication", recipient: user.email, token: otp.parse(data.token) }];
  }
  const hash = tokenHash.parse(data.token_hash);
  if (data.email_action_type === "email_change") {
    const newEmail = address.parse(user.new_email);
    const currentHash = tokenHash.parse(data.token_hash_new);
    otp.parse(data.token);
    otp.parse(data.token_new);
    return [
      { action: "email_change", recipient: user.email, tokenHash: currentHash, redirectTo: data.redirect_to, newEmail },
      { action: "email_change", recipient: newEmail, tokenHash: hash, redirectTo: data.redirect_to, newEmail },
    ];
  }
  if (data.email_action_type === "recovery" && data.redirect_to && data.redirect_to !== `${appOrigin}/auth/recovery`) throw new Error("Invalid recovery redirect");
  if (data.email_action_type === "signup" || data.email_action_type === "magiclink") {
    return [{ action: data.email_action_type, recipient: user.email, tokenHash: hash, redirectTo: data.redirect_to, token: otp.parse(data.token) }];
  }
  return [{ action: data.email_action_type, recipient: user.email, tokenHash: hash, redirectTo: data.redirect_to }];
}

const linkCopy = {
  invite: { subject: "Te invitaron a Cuadrao", paragraph: "Te invitaron a usar Cuadrao.", button: "Acepta aquí" },
  magiclink: { subject: "Tu enlace para entrar", button: "O entra aquí", security: "Si no lo pediste, ignora este correo." },
} as const;

export async function renderAuthMail(mail: AuthMail, supabaseUrl: string) {
  if (mail.action === "reauthentication") {
    return { subject: "Tu código de verificación", ...renderAccountEmail({
      title: "Tu código de verificación", paragraphs: [], code: mail.token,
    }) };
  }
  const url = new URL("/auth/v1/verify", supabaseUrl);
  url.searchParams.set("token", mail.tokenHash);
  url.searchParams.set("type", mail.action);
  url.searchParams.set("redirect_to", mail.redirectTo);
  if (mail.action === "recovery") return renderResetPasswordEmail(url.href);
  if (mail.action === "signup") {
    return { subject: `${mail.token} es tu código de Cuadrao`, ...renderAccountEmail({
      title: "Tu código de Cuadrao", code: mail.token,
      paragraphs: ["Úsalo para confirmar tu cuenta."],
      action: { label: "También puedes entrar aquí", url: url.href },
      expiryNote: "Vence en 60 minutos.",
      afterAction: "Si no creaste una cuenta, ignora este correo.",
    }) };
  }
  if (mail.action === "email_change") {
    return { subject: "Confirma tu nuevo correo", ...renderAccountEmail({
      title: "Confirma tu nuevo correo", paragraphs: ["Confirma que quieres usar este correo en Cuadrao."],
      action: { label: "Confirma tu nuevo correo", url: url.href },
      afterAction: "Si no lo pediste, escríbenos.",
    }) };
  }
  const copy = linkCopy[mail.action];
  return { subject: copy.subject, ...renderAccountEmail({
    title: copy.subject, code: mail.action === "magiclink" ? mail.token : undefined, paragraphs: "paragraph" in copy ? [copy.paragraph] : [], action: { label: copy.button, url: url.href },
    afterAction: "security" in copy ? copy.security : undefined,
  }) };
}
