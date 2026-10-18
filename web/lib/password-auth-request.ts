import { unauthenticatedApiFetch } from "./argus-api-transport";

export const PASSWORD_AUTH_REQUEST_TIMEOUT_MS = 45_000;

function stalledBrowserCheck(): Error & { code: string } {
  return Object.assign(new Error("The browser check did not finish."), {
    code: "captcha_unavailable",
  });
}

function isStalledPasswordRequest(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export async function postPasswordAuth<T>(
  path: string,
  body: unknown,
  timeoutMs = PASSWORD_AUTH_REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject(stalledBrowserCheck());
    }, timeoutMs);
  });
  const request = unauthenticatedApiFetch<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(
    (value) => value,
    (error: unknown) => {
      throw isStalledPasswordRequest(error) ? stalledBrowserCheck() : error;
    },
  );
  // The deadline can win first. A later abort must not reject unhandled.
  void request.catch(() => undefined);
  try {
    return await Promise.race([request, deadline]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
