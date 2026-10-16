"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type CaptchaApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string;
  remove: (id: string) => void;
};

export function WaitlistCaptcha({ onToken, attempt }: { onToken: (token: string) => void; attempt: number }) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onToken);
  const [siteKey, setSiteKey] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => { callback.current = onToken; }, [onToken]);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/signups/config", { signal: controller.signal }).then(async (response) => {
      const config: unknown = await response.json();
      if (response.ok && config && typeof config === "object" && "siteKey" in config && typeof config.siteKey === "string") setSiteKey(config.siteKey);
    }).catch(() => { callback.current(""); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const api = (window as Window & { turnstile?: CaptchaApi }).turnstile;
    if (!loaded || !siteKey || !api || !container.current) return;
    const id = api.render(container.current, {
      sitekey: siteKey,
      action: "personal_waitlist",
      size: "flexible",
      theme: "light",
      language: "es",
      callback: (token: string) => callback.current(token),
      "expired-callback": () => callback.current(""),
      "error-callback": () => callback.current(""),
    });
    return () => { api.remove(id); callback.current(""); };
  }, [attempt, loaded, siteKey]);

  return <>
    <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" onReady={() => setLoaded(true)} />
    <div ref={container} />
  </>;
}
