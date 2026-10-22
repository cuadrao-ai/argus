"use client";

import { useTranslation } from "react-i18next";
import { useTypewriter } from "@/components/ui/useTypewriter";

export function AuthHero({ mode }: { mode: "signup" | "login" }) {
  const { t, i18n } = useTranslation();
  const text = t(`auth.${mode}.hero`);
  return <HeroText key={`${i18n.resolvedLanguage}:${mode}`} text={text} />;
}

function HeroText({ text }: { text: string }) {
  const { visibleCount } = useTypewriter(text);
  return (
    <h2
      data-testid="auth-hero"
      className="font-display mb-[21px] text-balance text-[28px] font-medium leading-[1.2] tracking-tight text-[var(--cuadrao-green)] min-[80rem]:mb-[34px] min-[80rem]:text-[40px]"
    >
      <span className="sr-only">{text}</span>
      <span aria-hidden="true" className="whitespace-pre-line">
        {text.replaceAll(". ", ".\n").split("").map((character, index) => (
          <span key={index} className={`motion-reduce:!visible ${index < visibleCount ? "visible" : "invisible"}`}>
            {character}
          </span>
        ))}
      </span>
    </h2>
  );
}
