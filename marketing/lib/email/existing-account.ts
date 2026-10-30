import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout";
import accountCopy from "./account-copy.generated.json";

export function renderExistingAccountEmail(data: { signInUrl: string }, options: EmailLayoutOptions = {}) {
  const url = new URL(data.signInUrl);
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search !== "?auth=login" || url.hash) {
    throw new Error("Existing account email must open ordinary sign-in");
  }
  const copy = accountCopy[options.locale ?? "es-419"].existing_account;
  return {
    subject: copy.subject,
    ...renderAccountEmail({
      title: copy.title,
      preheader: copy.preheader,
      paragraphs: copy.paragraphs,
      action: { label: copy.cta, url: url.href },
      afterAction: copy.after_action,
    }, options),
  };
}
