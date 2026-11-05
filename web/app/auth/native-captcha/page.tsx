"use client";

import { useEffect } from "react";

import { beginNativeCaptcha } from "@/lib/native-captcha";

export default function NativeCaptchaPage() {
  useEffect(() => {
    const handler = window.webkit?.messageHandlers?.argusCaptcha;
    if (window.top !== window || !handler) return;
    return beginNativeCaptcha((message) => handler.postMessage(message));
  }, []);

  return null;
}
