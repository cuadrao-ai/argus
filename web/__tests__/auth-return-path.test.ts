import { describe, expect, test } from "bun:test";
import assert from "node:assert/strict";
import { readReturnPath } from "../lib/auth-return-path";
import { authLoginPathFromSearch, pathWithSearch } from "../lib/landing-intent";

describe("sign-in return path", () => {
  test("a signed-out Business receipt link returns to that receipt", () => {
    const login = authLoginPathFromSearch("?receipt=rcpt-123&utm_source=whatsapp", "/biz");
    const search = login.slice(login.indexOf("?"));
    expect(readReturnPath(search)).toBe("/biz?receipt=rcpt-123");
  });

  test("a signed-out canonical draft link returns to the same draft", () => {
    const id = "10000000-0000-4000-8000-000000000002";
    const login = authLoginPathFromSearch(`?draft=${id}&unexpected=drop&utm_source=whatsapp`, "/biz");
    assert.equal(readReturnPath(login.slice(login.indexOf("?"))), `/biz?draft=${id}`);
    assert.equal(login.includes("unexpected"), false);
    assert.equal(readReturnPath(`?return_to=${encodeURIComponent(`//evil.example/biz?draft=${id}`)}`), undefined);
    assert.equal(readReturnPath(`?return_to=${encodeURIComponent(`https://evil.example/biz?draft=${id}`)}`), undefined);
    assert.equal(readReturnPath(`?return_to=${encodeURIComponent("/biz?draft=<script>&unexpected=drop")}`), "/biz");
  });

  test("Business views and conversations survive; other query keys do not", () => {
    expect(readReturnPath("?return_to=%2Fbiz%3Fview%3Dinbox%26evil%3D1")).toBe("/biz?view=inbox");
    expect(readReturnPath("?return_to=%2Fbiz%3Fconversation%3Dabc-9")).toBe("/biz?conversation=abc-9");
  });

  test("unlisted paths and other origins are refused", () => {
    expect(readReturnPath("?return_to=%2F%2Fevil.example%2Fbiz")).toBeUndefined();
    expect(readReturnPath("?return_to=https%3A%2F%2Fevil.example%2Fbiz")).toBeUndefined();
    expect(readReturnPath("?return_to=%2Faccount%2Fsecurity")).toBeUndefined();
    expect(readReturnPath("?return_to=%2Fbiz%3Freceipt%3D%253Cscript%253E")).toBe("/biz");
  });

  test("chat sign-in keeps its existing shape", () => {
    expect(authLoginPathFromSearch("", "/chat")).toBe("/?from_path=%2Fchat&auth=login");
  });

  test("a refused return_to never rides into the chat URL", () => {
    expect(pathWithSearch("/chat", "?return_to=%2Faccount%2Fsecurity&utm_campaign=x&auth=login")).toBe(
      "/chat?utm_campaign=x",
    );
  });
});
