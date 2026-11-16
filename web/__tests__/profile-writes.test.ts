import { afterEach, describe, expect, test } from "bun:test";

import type { ApiUser } from "../lib/argus-api";
import {
  readProfile,
  saveProfile,
  saveProfileLanguage,
} from "../lib/profile-writes";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
let outstanding: Exchange[] = [];

// The queue belongs to the module, so a test that stops early must not leave a
// request unanswered for the next test to wait behind.
afterEach(async () => {
  for (let round = 0; round < 10; round += 1) {
    const open = outstanding.filter((request) => !request.answered);
    if (open.length === 0) break;
    for (const request of open) request.answer(refused());
    await settle();
  }
  outstanding = [];
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) {
    delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  } else {
    process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  }
});

const user = (overrides: Partial<ApiUser> = {}): ApiUser => ({
  id: "user-1",
  email: "a@b.c",
  username: "alex",
  display_name: "Alexandra",
  preferred_name: null,
  language: "es-419",
  locale: "es-419",
  onboarding: {
    completed: false,
    stage: "language_selection",
    language_confirmed: true,
    primary_goal: null,
  },
  ...overrides,
});

type Exchange = {
  method: string;
  body: unknown;
  answered: boolean;
  answer: (response: Response) => void;
};

/** Every request waits for the test to answer it. */
function holdRequests(): Exchange[] {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const sent: Exchange[] = [];
  globalThis.fetch = ((_url: string, init?: RequestInit) =>
    new Promise<Response>((resolve) => {
      const request: Exchange = {
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : null,
        answered: false,
        answer: (response) => {
          request.answered = true;
          resolve(response);
        },
      };
      sent.push(request);
      outstanding.push(request);
    })) as typeof fetch;
  return sent;
}

const requests = (sent: Exchange[]) =>
  sent.map(({ method, body }) => [method, body]);

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const profileReply = (profile: ApiUser) =>
  json(200, { user: profile, account_kind: "registered" });
const refused = () => json(503, { detail: "Profile store unavailable" });

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function pageLanguage(language: string) {
  const i18n = {
    language,
    async changeLanguage(next?: string) {
      if (next) i18n.language = next;
      return ((key: string) => key) as never;
    },
  };
  return i18n;
}

describe("the profile write path", () => {
  test("a request waits for the one ahead of it, even a refused one", async () => {
    const sent = holdRequests();
    const heard: ApiUser[] = [];

    const first = saveProfile({ display_name: "A" }, (u) => heard.push(u));
    const second = saveProfile({ preferred_name: "B" }, (u) => heard.push(u));
    await settle();
    expect(requests(sent)).toEqual([["PATCH", { display_name: "A" }]]);

    sent[0].answer(refused());
    await settle();
    // A failure is checked against the account before the queue moves on.
    expect(requests(sent)).toEqual([
      ["PATCH", { display_name: "A" }],
      ["GET", null],
    ]);
    sent[1].answer(profileReply(user()));
    await expect(first).rejects.toThrow();
    await settle();
    expect(requests(sent).at(-1)).toEqual(["PATCH", { preferred_name: "B" }]);

    sent[2].answer(profileReply(user({ preferred_name: "B" })));
    await second;
    expect(heard.map((u) => u.preferred_name)).toEqual(["B"]);
  });

  test("a read queues behind a pending save", async () => {
    const sent = holdRequests();

    const save = saveProfile({ display_name: "A" }, () => undefined);
    const read = readProfile();
    await settle();
    expect(sent).toHaveLength(1);

    sent[0].answer(profileReply(user({ display_name: "A" })));
    await save;
    await settle();
    expect(sent).toHaveLength(2);

    sent[1].answer(profileReply(user({ display_name: "A" })));
    expect((await read).user.display_name).toBe("A");
  });

  test("a save whose reply failed is kept when the account holds it", async () => {
    const sent = holdRequests();
    const heard: ApiUser[] = [];

    const save = saveProfile({ preferred_name: null }, (u) => heard.push(u));
    await settle();
    sent[0].answer(refused());
    await settle();
    sent[1].answer(profileReply(user({ preferred_name: null })));

    await save;
    expect(heard).toHaveLength(1);
  });

  test("a save stays refused when the account cannot be asked either", async () => {
    const sent = holdRequests();
    const heard: ApiUser[] = [];

    const save = saveProfile({ display_name: "A" }, (u) => heard.push(u));
    await settle();
    sent[0].answer(refused());
    await settle();
    sent[1].answer(refused());

    await expect(save).rejects.toThrow();
    expect(heard).toEqual([]);
  });

  test("a refused language is shown, then put back, and nothing is handed on", async () => {
    const sent = holdRequests();
    const i18n = pageLanguage("es-419");
    const heard: ApiUser[] = [];

    const outcome = saveProfileLanguage(i18n, "en", {
      onSaved: (u) => heard.push(u),
    });
    await settle();
    expect(i18n.language).toBe("en");
    expect(requests(sent)).toEqual([["PATCH", { language: "en", locale: "en-US" }]]);

    sent[0].answer(refused());
    await settle();
    sent[1].answer(profileReply(user({ language: "es-419" })));

    expect(await outcome).toBe(false);
    expect(i18n.language).toBe("es-419");
    expect(heard).toEqual([]);
  });

  test("a language the account took stays, even when its reply failed", async () => {
    const sent = holdRequests();
    const i18n = pageLanguage("es-419");
    const heard: ApiUser[] = [];

    const outcome = saveProfileLanguage(i18n, "en", {
      onSaved: (u) => heard.push(u),
    });
    await settle();
    sent[0].answer(refused());
    await settle();
    sent[1].answer(profileReply(user({ language: "en", locale: "en-US" })));

    expect(await outcome).toBe(true);
    expect(i18n.language).toBe("en");
    expect(heard.map((u) => u.language)).toEqual(["en"]);
  });

  test("a saved language stays and the saved profile is handed on", async () => {
    const sent = holdRequests();
    const i18n = pageLanguage("es-419");
    const heard: ApiUser[] = [];

    const outcome = saveProfileLanguage(i18n, "en", {
      onSaved: (u) => heard.push(u),
    });
    await settle();
    sent[0].answer(profileReply(user({ language: "en", locale: "en-US" })));

    expect(await outcome).toBe(true);
    expect(i18n.language).toBe("en");
    expect(heard.map((u) => u.language)).toEqual(["en"]);
  });

  test("an earlier refusal cannot undo a newer language", async () => {
    // Two panels opened one after the other can each start a save before the
    // first is answered.
    const sent = holdRequests();
    const i18n = pageLanguage("es-419");
    const heard: ApiUser[] = [];
    const onSaved = (u: ApiUser) => heard.push(u);

    const older = saveProfileLanguage(i18n, "en", { onSaved });
    const newer = saveProfileLanguage(i18n, "en", { onSaved });
    await settle();
    expect(requests(sent)).toEqual([["PATCH", { language: "en", locale: "en-US" }]]);

    sent[0].answer(refused());
    await settle();
    sent[1].answer(profileReply(user({ language: "es-419" })));
    expect(await older).toBe(false);
    await settle();

    expect(requests(sent).at(-1)).toEqual([
      "PATCH",
      { language: "en", locale: "en-US" },
    ]);
    sent[2].answer(profileReply(user({ language: "en", locale: "en-US" })));
    expect(await newer).toBe(true);
    expect(i18n.language).toBe("en");
    expect(heard.map((u) => u.language)).toEqual(["en"]);
  });
});
