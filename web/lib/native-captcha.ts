import { acquirePasswordAuthCaptchaToken } from "./guest-captcha";

export type NativeCaptchaMessage =
  | { type: "token"; token: string }
  | { type: "error" };

type NativeCaptchaHandler = { postMessage(message: NativeCaptchaMessage): void };

declare global {
  interface Window {
    webkit?: { messageHandlers?: { argusCaptcha?: NativeCaptchaHandler } };
  }
}

export function beginNativeCaptcha(
  postMessage: (message: NativeCaptchaMessage) => void,
  acquire: (signal: AbortSignal) => Promise<string> = acquirePasswordAuthCaptchaToken,
): () => void {
  const controller = new AbortController();
  const send = (message: NativeCaptchaMessage) => {
    if (controller.signal.aborted) return;
    try {
      postMessage(message);
    } catch {
      // The native view can detach its handler while acquisition settles.
    }
  };
  void acquire(controller.signal).then(
    (token) => send({ type: "token", token }),
    () => send({ type: "error" }),
  );
  return () => controller.abort();
}
