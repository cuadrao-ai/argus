"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CuadraoMark } from "@/components/CuadraoMark";
import { getMarketSession } from "@/lib/argus-api";
import {
  greetingAudience,
  greetingSlotForHour,
  pickGreetingKey,
  type DemonstratedInterest,
  type MarketSessionPhase,
} from "./greetingPool";


/* The empty chat greeting: the muted mark reuses the treatment from
 * ConversationRetrievalState (currentColor at low alpha), and the typewriter
 * greeting is the screen's one animated element. Screen readers get the full
 * sentence once through a polite status region, never character by character;
 * reduced motion renders the sentence instantly. */

const TYPE_INTERVAL_MS = 35;

// Cosmetic, so it speaks without the session rather than waiting on it.
const SESSION_TIMEOUT_MS = 2_000;

export default function EmptyChatGreeting({
  isGuest,
  preferredName,
}: {
  isGuest: boolean;
  /** What the user asked to be called. Blank means the nameless pool. */
  preferredName?: string | null;
}) {
  const { t } = useTranslation();
  const [greeting, setGreeting] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [done, setDone] = useState(false);
  const [session, setSession] = useState<MarketSessionPhase | null>(null);
  const [interest, setInterest] = useState<DemonstratedInterest | null>(null);
  const [sessionSettled, setSessionSettled] = useState(false);

  // Session and interest are backend truth; the client computes neither. A
  // guest's pool reads neither, and a visitor may have no identity to ask with.
  useEffect(() => {
    if (isGuest) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      SESSION_TIMEOUT_MS,
    );
    getMarketSession(controller.signal)
      .then((response) => {
        setSession(response.session?.phase ?? null);
        setInterest(response.interest ?? null);
      })
      .catch(() => {
        setSession(null);
        setInterest(null);
      })
      .finally(() => {
        window.clearTimeout(timeout);
        setSessionSettled(true);
      });
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [isGuest]);

  const settled = isGuest || sessionSettled;

  useEffect(() => {
    if (!settled) return;
    // Local clock only after mount: the server cannot know the visitor's hour,
    // and a mismatched SSR greeting would flash-correct on hydration.
    const now = new Date();
    const { name, marketFan } = greetingAudience({
      isGuest,
      preferredName,
      interest,
    });
    const key = pickGreetingKey({
      slot: greetingSlotForHour(now.getHours()),
      session,
      hasName: name.length > 0,
      marketFan,
      at: now,
    });
    const text = t(`chat.greeting.${key}`, {
      defaultValue: "What should we look into?",
      name,
    });
    setGreeting(text);
    const reduceMotion = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    )?.matches;
    if (reduceMotion) {
      setVisibleCount(text.length);
      setDone(true);
      return;
    }
    let shown = 0;
    const interval = window.setInterval(() => {
      shown += 1;
      setVisibleCount(shown);
      if (shown >= text.length) {
        window.clearInterval(interval);
        setDone(true);
      }
    }, TYPE_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [interest, isGuest, preferredName, session, settled, t]);

  return (
    <div
      className="mb-8 flex min-h-[108px] flex-col items-center gap-5"
      data-testid="empty-chat-greeting"
    >
      <CuadraoMark size={48} className="h-12 w-12" />
      <p
        aria-hidden="true"
        className="font-display min-h-[1.4em] text-balance text-center text-[24px] font-medium leading-[1.3] tracking-[-0.24px] text-black/80 sm:text-[28px] dark:text-white/80"
      >
        {greeting ? greeting.slice(0, visibleCount) : " "}
        {greeting && !done ? (
          <span
            aria-hidden="true"
            className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[0.18em] animate-pulse bg-black/40 motion-reduce:animate-none dark:bg-white/40"
          />
        ) : null}
      </p>
      <span className="sr-only" role="status">
        {greeting ?? ""}
      </span>
    </div>
  );
}
