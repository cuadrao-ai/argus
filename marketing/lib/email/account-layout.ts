export const emailPalette = {
  page: "#f7f5ee", card: "#ffffff", text: "#172b26", muted: "#56635e",
  grey: "#eef0ed", tint: "#e7f2df", darkPage: "#111c18", darkCard: "#172b26",
  darkText: "#fafbf8", darkMuted: "#cfdccf", darkGrey: "#293b33", darkTint: "#304834",
  darkAccent: "#b6e87a",
} as const;

type EmailContent = {
  title: string;
  preheader?: string;
  intro?: readonly string[];
  paragraphs: readonly string[];
  action?: { label: string; url: string };
  expiryNote?: string;
  afterAction?: string;
  beforeFooter?: string;
  postalAddress?: string;
};
export type AccountEmail = EmailContent & (
  | { code?: string; unsubscribeUrl?: never }
  | { code?: never; unsubscribeUrl: string }
);

const font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,Helvetica,sans-serif";
export type EmailLayoutOptions = { assetOrigin?: string; postalAddress?: string };

function emailAssets(options: EmailLayoutOptions): string {
  const value = options.assetOrigin ?? (process.env.CUADRAO_EMAIL_ASSET_ORIGIN || "https://cuadrao.ai");
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash || /[\r\n]/.test(value)) {
    throw new Error("Email image origin must be an HTTPS origin without credentials or a path");
  }
  return `${url.origin}/email`;
}
const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]!);

function safeUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || /[\r\n]/.test(value)) {
    throw new Error("Email links must use HTTPS without credentials");
  }
  return escapeHtml(url.href);
}

export function renderAccountEmail(content: AccountEmail, options: EmailLayoutOptions = {}): { html: string; text: string } {
  const assets = emailAssets(options);
  if (content.code !== undefined && (!/^\d{6,10}$/.test(content.code) || content.unsubscribeUrl)) {
    throw new Error("Invalid account email code");
  }
  const postalAddress = content.postalAddress?.trim() || options.postalAddress?.trim() || process.env.MARKETING_POSTAL_ADDRESS?.trim();
  if (!postalAddress || /^Cuadrao LLC[,\s]*$/i.test(postalAddress) || /[\r\n]/.test(postalAddress)) throw new Error("Email postal address configuration is required");
  const legalLine = /^Cuadrao LLC(?:,|$)/.test(postalAddress) ? postalAddress : `Cuadrao LLC, ${postalAddress}`;
  const p = emailPalette;
  const paragraph = (value: string) => `<p class="copy" style="margin:0 0 20px;color:${p.text};font-size:16px;line-height:24px">${escapeHtml(value)}</p>`;
  const muted = (value: string) => `<p class="muted" style="margin:16px 0;color:${p.muted};font-size:14px;line-height:21px">${escapeHtml(value)}</p>`;
  const dark = `
    .page{background:${p.darkPage}!important}.card,.footer{background:${p.darkCard}!important}
    .copy{color:${p.darkText}!important}.title{color:${p.darkAccent}!important}
    .muted,.muted a{color:${p.darkMuted}!important}.fallback{background:${p.darkGrey}!important;color:${p.darkText}!important}
    .code{background:${p.darkTint}!important;color:${p.darkText}!important}
    .button{background:${p.darkAccent}!important;color:${p.text}!important}
    .logo-light{display:none!important}.logo-dark{display:block!important;max-height:none!important}
  `;
  let action = "";
  if (content.action) {
    const href = safeUrl(content.action.url);
    const label = escapeHtml(content.action.label);
    action = `<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:4px 0 20px">
<!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="${href}" style="height:48px;v-text-anchor:middle;width:496px" arcsize="16%" stroke="f" fillcolor="${p.text}"><w:anchorlock/><center style="color:#ffffff;font-family:Arial,sans-serif;font-size:16px;font-weight:bold">${label}</center></v:roundrect><![endif]-->
<!--[if !mso]><!--><a class="button" href="${href}" style="display:block;box-sizing:border-box;width:100%;min-height:48px;padding:12px 16px;border-radius:8px;background:${p.text};color:#ffffff;font-size:16px;line-height:24px;font-weight:700;text-decoration:none;text-align:center">${label}</a><!--<![endif]-->
</td></tr></table><p class="fallback" style="margin:0 0 20px;padding:16px;background:${p.grey};color:${p.text};border-radius:8px;font-size:14px;line-height:21px;overflow-wrap:anywhere;word-break:break-all"><a class="fallback" href="${href}" style="color:${p.text};text-decoration:underline;overflow-wrap:anywhere;word-break:break-all">${href}</a></p>`;
  }
  const address = muted(legalLine);
  const leave = content.unsubscribeUrl
    ? `<p class="muted" style="margin:12px 0 0;color:${p.muted};font-size:14px;line-height:21px"><a href="${safeUrl(content.unsubscribeUrl)}" style="color:inherit;text-decoration:underline">Salir de la lista</a></p>` : "";
  const code = content.code
    ? `<p class="code" style="margin:0 0 20px;padding:20px 12px;border-radius:8px;background:${p.tint};color:${p.text};font-size:32px;line-height:40px;font-weight:700;letter-spacing:4px;text-align:center;white-space:nowrap">${content.code}</p>` : "";
  const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${escapeHtml(content.title)}</title><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark"><style>@media(prefers-color-scheme:dark){${dark}}${dark.replace(/(^|\})\s*([^{}]+)\{/g, (_, end, selectors) => `${end}${selectors.split(",").map((selector: string) => `[data-ogsc] ${selector.trim()}`).join(",")}{`)}</style></head>
<body class="page" style="margin:0;padding:32px 12px;background:${p.page};font-family:${font}">${content.preheader ? `<div class="preheader" style="display:none;max-height:0;overflow:hidden;mso-hide:all;opacity:0;color:transparent">${escapeHtml(content.preheader)}</div>` : ""}<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center"><table class="card" role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:${p.card};border-radius:12px;overflow:hidden"><tr><td style="padding:24px 32px;background:${p.text};border-radius:12px 12px 0 0">
<img class="logo-light" src="${assets}/wordmark-light.png" alt="Cuadrao" width="168" height="36" style="display:block;border:0;color:#fafbf8;font-size:24px;font-weight:bold">
<!--[if !mso]><!--><img class="logo-dark" src="${assets}/wordmark-dark.png" alt="Cuadrao" width="168" height="36" style="display:none;max-height:0;overflow:hidden;border:0;color:#fafbf8;font-size:24px;font-weight:bold"><!--<![endif]-->
</td></tr><tr><td style="padding:28px 32px 8px"><h1 class="title" style="margin:0 0 24px;color:${p.text};font-size:24px;line-height:32px;font-weight:700">${escapeHtml(content.title)}</h1>${(content.intro ?? []).map(paragraph).join("")}${code}${content.code && content.expiryNote ? muted(content.expiryNote) : ""}${content.paragraphs.map(paragraph).join("")}${action}${!content.code && content.expiryNote ? muted(content.expiryNote) : ""}${content.afterAction ? muted(content.afterAction) : ""}${content.beforeFooter ? paragraph(content.beforeFooter) : ""}</td></tr><tr><td class="footer" style="padding:20px 32px 28px;background:${p.card}"><p class="copy" style="margin:0 0 12px;color:${p.text};font-size:16px;line-height:24px">Saludos,<br>Cuadrao</p><p class="muted" style="margin:0;color:${p.muted};font-size:14px;line-height:21px">¿Necesitas ayuda? Escríbenos a <a href="mailto:hola@cuadrao.ai" style="color:inherit;text-decoration:underline">hola@cuadrao.ai</a></p>${address}${leave}</td></tr></table></td></tr></table></body></html>`;
  const text = [content.title, ...(content.intro ?? []), content.code, content.code && content.expiryNote, ...content.paragraphs,
    content.action && `${content.action.label}\n${content.action.url}`,
    !content.code && content.expiryNote, content.afterAction, content.beforeFooter,
    "Saludos,\nCuadrao", "¿Necesitas ayuda? Escríbenos a hola@cuadrao.ai",
    legalLine,
    content.unsubscribeUrl && `Salir de la lista\n${content.unsubscribeUrl}`,
  ].filter(Boolean).join("\n\n");
  return { html, text };
}
