'use client';

import { ReactNode, useEffect, useState } from 'react';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { documentLanguage, rememberShownLanguage, resolveLanguage } from '@/lib/language-features';

export function I18nProvider({ children }: { children: ReactNode }) {
  const [isInitialized, setIsInitialized] = useState(false);
  useEffect(() => {
    const syncDocumentLanguage = (language?: string) => {
      const shown = resolveLanguage({ device: language ?? i18n.resolvedLanguage ?? i18n.language });
      document.documentElement.lang = documentLanguage(shown, true);
      rememberShownLanguage(shown);
    };

    const handleInitialized = () => {
      syncDocumentLanguage();
      setIsInitialized(true);
    };

    if (i18n.isInitialized) {
      handleInitialized();
    } else {
      i18n.on('initialized', handleInitialized);
    }

    i18n.on('languageChanged', syncDocumentLanguage);

    // Refresh development copy without remounting forms or losing open drafts.
    const controller = new AbortController();
    const refreshCopy = async () => {
      if (process.env.NODE_ENV !== 'development' || !i18n.isInitialized) return;
      const language = i18n.resolvedLanguage ?? i18n.language;
      try {
        const response = await fetch(`/locales/${language}/common.json`, {
          cache: 'no-store',
          signal: controller.signal,
        });
        if (!response.ok) return;
        const resources = await response.json();
        if (controller.signal.aborted || language !== (i18n.resolvedLanguage ?? i18n.language)) return;
        if (JSON.stringify(resources) === JSON.stringify(i18n.getResourceBundle(language, 'common'))) return;
        i18n.addResourceBundle(language, 'common', resources, true, true);
        i18n.emit('languageChanged', i18n.language);
      } catch {
        // Keep the currently loaded copy when the development server is unavailable.
      }
    };
    if (process.env.NODE_ENV === 'development') {
      void refreshCopy();
      window.addEventListener('focus', refreshCopy);
    }

    return () => {
      controller.abort();
      window.removeEventListener('focus', refreshCopy);
      i18n.off('initialized', handleInitialized);
      i18n.off('languageChanged', syncDocumentLanguage);
    };
  }, []);

  if (!isInitialized) {
    // Show a blank screen or a loading shimmer that matches Argus aesthetics
    return <div className="bg-[#191c1f] min-h-full" />;
  }

  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}
