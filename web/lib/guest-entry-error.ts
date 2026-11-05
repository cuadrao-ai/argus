import { useCallback, useState, type MutableRefObject } from "react";

import {
  CAPTCHA_UNAVAILABLE_CODE,
  guestEntryErrorKind,
  type GuestEntryErrorKind,
} from "./guest-captcha";

export { CAPTCHA_UNAVAILABLE_CODE, guestEntryErrorKind };
export type { GuestEntryErrorKind };

export function applyGuestBootstrapError(
  error: unknown,
  retryRef: { current: unknown },
): GuestEntryErrorKind {
  const kind = guestEntryErrorKind(error);
  if (kind === CAPTCHA_UNAVAILABLE_CODE) {
    retryRef.current = null;
  }
  return kind;
}

export function useGuestEntryError(retryRef: MutableRefObject<unknown>) {
  const [guestSubmissionError, setGuestSubmissionError] =
    useState<GuestEntryErrorKind | null>(null);

  const clearGuestSubmissionError = useCallback(() => {
    setGuestSubmissionError(null);
  }, []);
  const resetGuestSubmissionError = useCallback(() => {
    retryRef.current = null;
    setGuestSubmissionError(null);
  }, [retryRef]);
  const onGuestBootstrapError = useCallback(
    (error?: unknown) => {
      setGuestSubmissionError(applyGuestBootstrapError(error, retryRef));
    },
    [retryRef],
  );

  return {
    guestSubmissionError,
    clearGuestSubmissionError,
    resetGuestSubmissionError,
    onGuestBootstrapError,
  };
}
