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

/** The person arrives at this address, and the page takes the invite it names. */
function arrive(address: string) {
  window.history.replaceState(null, "", address);
  capturePendingInvite();
}
const address = () => `${window.location.pathname}${window.location.search}`;

test.each(["login", "signup"] as const)("the invite is kept from the front door through %s", (entry) => {
  const door = frontDoor(`?invite=${INVITE}`, entry);
  arrive(door);
  expect(address()).toBe(door);

  // A confirmation email opens the app in a new tab with no return address.
  arrive("/");
  arrive("/biz");
  expect(pendingInviteId()).toBe(INVITE);
});

test("a signed-in person's link moves from the Business address into the store", () => {
  arrive(`/biz?invite=${INVITE.toUpperCase()}&view=inbox#top`);

  expect(pendingInviteId()).toBe(INVITE);
  expect(address()).toBe("/biz?view=inbox");
  expect(window.location.hash).toBe("#top");
  forgetPendingInvite();
  expect(pendingInviteId()).toBeNull();
});

test("an answered invite does not come back when the page loads again", () => {
  arrive(`/biz?invite=${INVITE}`);
  forgetPendingInvite();
  capturePendingInvite();

  expect(pendingInviteId()).toBeNull();
  expect(address()).toBe("/biz");
});

test.each([
  ["/biz?invite=not-an-id", "/biz"],
  ["/biz?invite=<script>&view=inbox", "/biz?view=inbox"],
  [`/?return_to=${encodeURIComponent(`//evil.example/biz?invite=${INVITE}`)}`, null],
  [`/?return_to=${encodeURIComponent(`/account?invite=${INVITE}`)}`, null],
  [`/?invite=${INVITE}`, null],
])("%s names no invite", (arrival, left) => {
  arrive(arrival);

  expect(pendingInviteId()).toBeNull();
  expect(address()).toBe(left ?? arrival);
});
