import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import HttpBackend from 'i18next-http-backend';
import { DEFAULT_LANGUAGE, ENABLED_LANGUAGE_CODES, browserLanguageSources, fallbackChain, resolveLanguage } from './language-features';

i18n
  .use(HttpBackend)
  .use(initReactI18next)
  .init({
    // The server has no sources, so it starts on the default the layout renders.
    lng: resolveLanguage(browserLanguageSources()),
    fallbackLng: (code?: string) => fallbackChain(code, DEFAULT_LANGUAGE),
    supportedLngs: ENABLED_LANGUAGE_CODES,
    defaultNS: 'common',
    ns: ['common'],
    interpolation: {
      escapeValue: false,
    },
    // Missing keys resolve to "" (falsy), so `t(dynamicKey) || t(fallback)`
    // actually falls back instead of rendering the raw key.
    parseMissingKeyHandler: () => '',
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },
  });

export default i18n;
