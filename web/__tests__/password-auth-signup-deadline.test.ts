import { afterEach, beforeEach, describe, expect, jest, spyOn, test } from "bun:test";
import { loginWithEmail, signupWithEmail } from "../lib/argus-api";
import { PASSWORD_AUTH_REQUEST_TIMEOUT_MS } from "../lib/password-auth-request";

const originalNodeEnv = process.env.NODE_ENV;

beforeEach(() => {
  process.env.NODE_ENV = "test";
  jest.useFakeTimers();
});

afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
  if (originalNodeEnv === undefined) delete process.env.NODE_ENV;
  else process.env.NODE_ENV = originalNodeEnv;
});

function delayedServerResponse(body: unknown, status = 200) {
  let started!: () => void;
  const requestStarted = new Promise<void>((resolve) => { started = resolve; });
  const request = spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
    const response = new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(() => {
        resolve(Response.json(body, { status }));
      }, PASSWORD_AUTH_REQUEST_TIMEOUT_MS + 1);
      init?.signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      }, { once: true });
    });
    started();
    return response;
  });
  return { request, requestStarted };
}

const signup = { email: "signup@example.test", password: "test-password", language: "es-419" as const };

describe("password auth request deadlines", () => {
  test.each([null, {}])("signup preserves a late server answer with session %j", async (session) => {
    const answer = { user: { id: "signup-user" }, session };
    const { request, requestStarted } = delayedServerResponse(answer);
    const result = signupWithEmail(signup).then(
      (value) => ({ value }),
      (error: unknown) => ({ error }),
    );

    await requestStarted;
    jest.advanceTimersByTime(PASSWORD_AUTH_REQUEST_TIMEOUT_MS + 1);

    expect(await result).toEqual({
      value: { response: answer, needsEmailConfirmation: session === null },
    });
    expect(request).toHaveBeenCalledTimes(1);
    expect(String(request.mock.calls[0][0])).toEndWith("/auth/signup");
    expect(request.mock.calls[0][1]?.method).toBe("POST");
    expect(JSON.parse(String(request.mock.calls[0][1]?.body))).toMatchObject(signup);
    expect(request.mock.calls[0][1]?.signal).toBeUndefined();
  });

  test("signup preserves a late server refusal", async () => {
    const { requestStarted } = delayedServerResponse({ code: "signup_disabled", detail: "Signup disabled" }, 403);
    const result = signupWithEmail(signup).catch((error: unknown) => error);

    await requestStarted;
    jest.advanceTimersByTime(PASSWORD_AUTH_REQUEST_TIMEOUT_MS + 1);

    expect(await result).toMatchObject({ code: "signup_disabled", status: 403 });
  });

  test("sign-in still aborts at its existing default deadline", async () => {
    const { request, requestStarted } = delayedServerResponse({ session: null });
    let settled = false;
    const result = loginWithEmail({ email: signup.email, password: signup.password })
      .catch((error: unknown) => error)
      .finally(() => { settled = true; });

    await requestStarted;
    jest.advanceTimersByTime(PASSWORD_AUTH_REQUEST_TIMEOUT_MS - 1);
    await Promise.resolve();
    expect(settled).toBe(false);
    expect(request.mock.calls[0][1]?.signal?.aborted).toBe(false);

    jest.advanceTimersByTime(1);
    expect(await result).toMatchObject({ code: "captcha_unavailable" });
    expect(request.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
});
