import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout";
import accountCopy from "./account-copy.generated.json";

export type BusinessClosedEmailData = {
  businessName: string;
  ownerName: string;
  closedDate: string;
  purgeDate: string;
};

export function renderBusinessClosedEmail(data: BusinessClosedEmailData, options: EmailLayoutOptions = {}) {
  if (Object.values(data).some(value => !value.trim() || /[\r\n]/.test(value))) {
    throw new Error("Business close email fields must be nonempty single-line values");
  }
  const subject = `${data.businessName} se cerró en Cuadrao`;
  const body = `Hola, ${data.ownerName} cerró ${data.businessName} en Cuadrao el ${data.closedDate}, y ya no tienes acceso. Si necesitas copias de los comprobantes, pídeselas a ${data.ownerName}. Si el negocio no se reabre antes del ${data.purgeDate}, sus datos se borrarán. Saludos, Cuadrao`;
  return { subject, ...renderAccountEmail({ title: subject, paragraphs: [body] }, options) };
}

export type BusinessLifecycleEmailData = {
  businessName: string;
  ownerName: string;
  actionUrl: string;
} & (
  | { kind: "member_reopened" }
  | { kind: "owner_closed" | "purge_reminder"; closedDate: string; purgeDate: string; purgeTime: string }
);

function navigationUrl(data: BusinessLifecycleEmailData): string {
  const url = new URL(data.actionUrl);
  const parameters = [...url.searchParams];
  const memberLink = data.kind === "member_reopened";
  const business = url.searchParams.get("business") ?? "";
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/biz" || /[#\\\s]/.test(data.actionUrl)
    || (memberLink ? parameters.length !== 0 || data.actionUrl.includes("?")
      : parameters.length !== 2 || url.searchParams.get("lifecycle") !== "manage" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(business)
        || parameters.some(([key]) => key !== "lifecycle" && key !== "business"))) {
    throw new Error("Business email links must navigate to the expected business page");
  }
  return url.href;
}

export function renderBusinessLifecycleEmail(data: BusinessLifecycleEmailData, options: EmailLayoutOptions = {}) {
  if (Object.values(data).some(value => !value.trim() || [...value].some(character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127))) {
    throw new Error("Business email fields must be nonempty single-line values");
  }
  const copy = accountCopy[options.locale ?? "es-419"].business_lifecycle[data.kind];
  const replace = (value: string) => value.replace(/\{(businessName|ownerName|closedDate|purgeDate|purgeTime)\}/g, (_, key: string) => {
    switch (key) {
      case "businessName": return data.businessName;
      case "ownerName": return data.ownerName;
      case "closedDate": return data.kind === "member_reopened" ? "" : data.closedDate;
      case "purgeDate": return data.kind === "member_reopened" ? "" : data.purgeDate;
      case "purgeTime": return data.kind === "member_reopened" ? "" : data.purgeTime;
      default: throw new Error("Unsupported business email placeholder");
    }
  });
  return {
    subject: replace(copy.subject),
    ...renderAccountEmail({title: replace(copy.title), preheader: replace(copy.preheader), paragraphs: copy.paragraphs.map(replace), action: {label: copy.cta, url: navigationUrl(data)}}, options),
  };
}
