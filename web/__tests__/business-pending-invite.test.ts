import { afterAll, beforeAll, beforeEach, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

import { readReturnPath } from "@/lib/auth-return-path";
import { capturePendingInvite, forgetPendingInvite, pendingInviteId } from "@/lib/business-pending-invite";
import { authLoginPathFromSearch } from "@/lib/landing-intent";

const INVITE = "0586f5ef-c65c-4d7f-9aec-d453124e3ff3";

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/" }); });
afterAll(async () => { await GlobalRegistrator.unregister(); });
beforeEach(() => { forgetPendingInvite(); });

/** The front-door address a signed-out visit to the email link is sent to. */
const frontDoor = (link: string, entry: "login" | "signup") => authLoginPathFromSearch(link, "/biz", entry);
const searchOf = (address: string) => address.slice(address.indexOf("?"));

test("a new person's link opens sign-up and returns to the app with that invite", () => {
  const door = frontDoor(`?invite=${INVITE}&auth=signup`, "signup");

  expect(new URLSearchParams(searchOf(door)).get("auth")).toBe("signup");
  expect(readReturnPath(searchOf(door))).toBe(`/biz?invite=${INVITE}`);
});

test("an existing person's link opens sign-in and returns to the app with that invite", () => {
  const door = frontDoor(`?invite=${INVITE}`, "login");

  expect(new URLSearchParams(searchOf(door)).get("auth")).toBe("login");
  expect(readReturnPath(searchOf(door))).toBe(`/biz?invite=${INVITE}`);
});

test.each(["login", "signup"] as const)("the invite is kept from the front door through %s", (entry) => {
  capturePendingInvite("/", searchOf(frontDoor(`?invite=${INVITE}`, entry)));

  // A confirmation email opens the app in a new tab with no return address.
  capturePendingInvite("/", "");
  capturePendingInvite("/biz", "");
  expect(pendingInviteId()).toBe(INVITE);
});

test("a signed-in person's link is kept from the Business address", () => {
  capturePendingInvite("/biz", `?invite=${INVITE.toUpperCase()}&view=inbox`);

  expect(pendingInviteId()).toBe(INVITE);
  forgetPendingInvite();
  expect(pendingInviteId()).toBeNull();
});

test.each([
  ["/biz", "?invite=not-an-id"],
  ["/biz", "?invite=<script>"],
  ["/", `?return_to=${encodeURIComponent(`//evil.example/biz?invite=${INVITE}`)}`],
  ["/", `?return_to=${encodeURIComponent(`/account?invite=${INVITE}`)}`],
  ["/", `?invite=${INVITE}`],
])("%s%s names no invite", (pathname, search) => {
  capturePendingInvite(pathname, search);

  expect(pendingInviteId()).toBeNull();
});
