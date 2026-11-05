"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { readSessionStored, writeSessionStored } from "@/lib/browser-storage";
import { useTypewriter } from "@/components/ui/useTypewriter";
import type { GreetingPeriod } from "./home-greeting";

const APPEARED_KEY = "cuadrao:home-greeting-seen";
let seenWithoutStorage = false;
type Appearance = { kind: "pending" } | { kind: "typing"; text: string } | { kind: "settled" };

function claimFirstAppearance(): boolean {
  if (seenWithoutStorage || readSessionStored(APPEARED_KEY) === "1") return false;
  if (!writeSessionStored(APPEARED_KEY, "1")) seenWithoutStorage = true;
  return true;
}

export default function HomeGreeting({ period, name }: { period: GreetingPeriod | null; name?: string | null }) {
  const { t } = useTranslation();
  const greeting = period ? t(`business.overview.greetings.${period}`) : "";
  const preferredName = name?.trim();
  const text = preferredName && greeting ? t("business.overview.greeting_named", { greeting, name: preferredName }) : greeting;
  const [appearance, setAppearance] = useState<Appearance>({ kind: "pending" });
  const firstAppearance = useRef<Appearance | null>(null);

  useEffect(() => {
    if (!text) return;
    const show = () => {
      if (document.visibilityState === "hidden") return;
      if (firstAppearance.current === null) {
        const first = claimFirstAppearance();
        firstAppearance.current = first && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
          ? { kind: "typing", text }
          : { kind: "settled" };
      }
      setAppearance((current) => current.kind === "pending" ? firstAppearance.current! : current.kind === "typing" && current.text !== text ? { kind: "settled" } : current);
    };
    show();
    document.addEventListener("visibilitychange", show);
    return () => document.removeEventListener("visibilitychange", show);
  }, [text]);

  if (!text) return <span aria-hidden="true" style={{ display: "inline-block", minHeight: "1.2em" }} />;
  if (appearance.kind === "pending") return <span data-greeting-state="pending"><span className="sr-only">{text}</span><span aria-hidden="true" style={{ visibility: "hidden" }}>{text}</span></span>;
  if (appearance.kind === "typing" && appearance.text === text) {
    return <TypedGreeting text={text} onComplete={() => setAppearance({ kind: "settled" })} />;
  }
  return <span data-greeting-state={appearance.kind}>{text}</span>;
}

function TypedGreeting({ text, onComplete }: { text: string; onComplete: () => void }) {
  const { visibleCount, done } = useTypewriter(text);
  useEffect(() => { if (done) onComplete(); }, [done, onComplete]);
  return (
    <span data-greeting-state="typing">
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {text.split("").map((character, index) => <span key={index} className={`motion-reduce:!visible ${index < visibleCount ? "visible" : "invisible"}`}>{character}</span>)}
      </span>
    </span>
  );
}
