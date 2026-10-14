import { render, toPlainText } from "@react-email/render";
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

type LinkedAction = "signup" | "invite" | "magiclink" | "recovery";
export type AuthMail =
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
  return [{ action: data.email_action_type, recipient: user.email, tokenHash: hash, redirectTo: data.redirect_to }];
}

const existingLinkCopy = {
  signup: { subject: "Confirm your email address", title: "Confirm your email address", paragraph: "Follow the link below to confirm this email address and finish signing up.", button: "Confirm email address" },
  invite: { subject: "You've been invited", title: "You've been invited", paragraph: "You've been invited to create an account. Follow the link below to accept.", button: "Accept invitation" },
  magiclink: { subject: "Your sign-in link", title: "Your sign-in link", paragraph: "Follow the link below to sign in. This link expires shortly and can only be used once.", button: "Sign in" },
} as const;

export async function renderAuthMail(mail: AuthMail, supabaseUrl: string) {
  if (mail.action === "reauthentication") {
    const html = await render(<><h2>Your verification code</h2><p>Use the code below to verify your identity. It expires shortly.</p><p>{mail.token}</p></>);
    return { subject: `${mail.token} is your verification code`, html, text: toPlainText(html) };
  }
  const url = new URL("/auth/v1/verify", supabaseUrl);
  url.searchParams.set("token", mail.tokenHash);
  url.searchParams.set("type", mail.action);
  url.searchParams.set("redirect_to", mail.redirectTo);
  if (mail.action === "recovery") return renderResetPasswordEmail(url.href);
  if (mail.action === "email_change") {
    const html = await render(<><h2>Confirm your new email address</h2><p>Follow the link below to confirm {mail.newEmail} as your new email address.</p><p><a href={url.href}>Confirm new email address</a></p><p>If you didn&apos;t request this change, you can safely ignore this email.</p></>);
    return { subject: "Confirm your new email address", html, text: toPlainText(html) };
  }
  const copy = existingLinkCopy[mail.action];
  const html = await render(<><h2>{copy.title}</h2><p>{copy.paragraph}</p><p><a href={url.href}>{copy.button}</a></p></>);
  return { subject: copy.subject, html, text: toPlainText(html) };
}
