import { businessContent, type BusinessLocale } from "../components/content";
import { businessPath, type BusinessPage } from "./site-routes";

export type LanguageSwitch = {
  href: string;
  label: string;
  lang: BusinessLocale;
  phoneLabel: string;
};

export function languageSwitch(locale: BusinessLocale, page: BusinessPage): LanguageSwitch {
  const other: BusinessLocale = locale === "es" ? "en" : "es";
  const copy = businessContent[locale].navigation;
  return {
    href: businessPath(other, page),
    label: copy.otherLanguage,
    lang: other,
    phoneLabel: copy.changeLanguage,
  };
}
