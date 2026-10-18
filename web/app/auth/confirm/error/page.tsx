"use client";

import Link from "next/link";
import { useTranslation } from "react-i18next";

import { inlineFailureTextClass } from "@/lib/failure-treatment";

export default function ConfirmErrorPage() {
  const { t } = useTranslation();
  return (
    <main className="flex min-h-[100dvh] items-center justify-center px-6 py-12">
      <section className="w-full max-w-md rounded-[24px] border border-black/10 bg-white p-7 dark:border-white/10 dark:bg-[#151719]">
        <h1 className="font-display text-3xl font-medium tracking-tight text-black dark:text-white">
          {t("auth.confirm.error_title", "This link didn’t work")}
        </h1>
        <p role="alert" className={`mt-4 text-sm leading-relaxed ${inlineFailureTextClass}`}>
          {t(
            "auth.confirm.error_body",
            "It is missing, expired, or already used. Ask for a new one and try again.",
          )}
        </p>
        <Link
          href="/?auth=login"
          className="mt-5 inline-flex rounded-full bg-black px-5 py-3 text-sm font-medium text-white dark:bg-white dark:text-black"
        >
          {t("auth.confirm.back_to_sign_in", "Back to sign in")}
        </Link>
      </section>
    </main>
  );
}
