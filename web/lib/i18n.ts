import { LANGUAGE_STORAGE_KEY } from './browser-storage';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import HttpBackend from 'i18next-http-backend';
import { DEFAULT_LANGUAGE, ENABLED_LANGUAGE_CODES, LANGUAGE_DETECTION_ORDER, fallbackChain, LANGUAGE_DETECTION_CACHES } from './language-features';

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    // Nothing saved falls to the default through this chain.
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
    detection: {
      order: [...LANGUAGE_DETECTION_ORDER],
      caches: [...LANGUAGE_DETECTION_CACHES],
      // Declared rather than inherited, so the key the detector persists is
      // one the storage registry knows about.
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      // Language comes from what the user actually set, not from geography.
      // navigator.language of es-MX or es-ES is still Spanish, so it resolves
      // to the one Spanish Argus ships. A transform on the detected value, so
      // it adds no second route to the key above.
      convertDetectedLanguage: (language: string) =>
        language.toLowerCase().startsWith('es') ? 'es-419' : language,
    },
  });

export default i18n;
