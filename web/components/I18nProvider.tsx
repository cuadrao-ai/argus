'use client';

import { ReactNode, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { documentLanguage } from '@/lib/language-features';
import { businessPilotEnabled } from '@/lib/private-alpha-flags';
import { PUBLIC_RECEIPT_PATH_PREFIX } from '@/lib/public-receipt-contract';

export function I18nProvider({ children }: { children: ReactNode }) {
  const [isInitialized, setIsInitialized] = useState(false);
  const pathname = usePathname();
  // Public receipts resolve their copy on the server and consume no i18next
  // resources, so they must not wait on client initialization. Holding them behind
  // the gate below left a shared link blank until JavaScript ran, and permanently
  // blank when it is blocked or fails, which is the opposite of what a public page
  // opened from a message needs. Every other route keeps the gate.
  const rendersWithoutI18n = Boolean(
    pathname?.startsWith(PUBLIC_RECEIPT_PATH_PREFIX),
  );

  useEffect(() => {
    const syncDocumentLanguage = (language?: string) => {
      document.documentElement.lang = documentLanguage(
        language ?? i18n.resolvedLanguage ?? i18n.language,
        businessPilotEnabled,
      );
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

    return () => {
      i18n.off('initialized', handleInitialized);
      i18n.off('languageChanged', syncDocumentLanguage);
    };
  }, []);

  if (!isInitialized && !rendersWithoutI18n) {
    // Show a blank screen or a loading shimmer that matches Argus aesthetics
    return <div className="bg-[#191c1f] min-h-full" />;
  }

  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}
