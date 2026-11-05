import { describe, expect, test } from "bun:test";

import {
  authLinkErrorRedirect,
  confirmErrorView,
  confirmReference,
  rendersOwnLinkError,
  mapAuthLinkError,
  notFoundHref,
  prefilledEmail,
} from "@/lib/auth-link-error";

const origin = "https://app.example.test";

describe("mapAuthLinkError", () => {
  test("access_denied on the recovery path asks for a new recovery link", () => {
    expect(
      mapAuthLinkError({
        search: "?error=access_denied",
        hash: "",
        pathname: "/auth/recovery",
      }),
    ).toEqual({
      problem: "expired",
      kind: "request",
      flow: "recovery",
      email: null,
      href: "/auth/forgot-password",
    });
  });

  test("otp_expired in the hash is a recovery request when type says so", () => {
    expect(
      mapAuthLinkError({
        search: "",
        hash: "#error_code=otp_expired&type=recovery&email=ada@example.test",
        pathname: "/",
      }),
    ).toEqual({
      problem: "expired",
      kind: "request",
      flow: "recovery",
      email: "ada@example.test",
      href: "/auth/forgot-password?email=ada%40example.test",
    });
  });

  test("otp_expired for an email change keeps the address from the url", () => {
    expect(
      mapAuthLinkError({
        search: "?error_code=otp_expired&type=email_change&email=ada@example.test",
        hash: "",
        pathname: "/",
        knownEmail: "other@example.test",
      }),
    ).toEqual({
      problem: "expired",
      kind: "request",
      flow: "email_change",
      email: "ada@example.test",
      href: "/account/security?email=ada%40example.test",
    });
  });

  test("a known session address fills an email change that arrived without one", () => {
    expect(
      mapAuthLinkError({
        search: "?error=access_denied&type=email_change",
        hash: "",
        pathname: "/",
        knownEmail: "ada@example.test",
      }),
    ).toEqual({
      problem: "expired",
      kind: "request",
      flow: "email_change",
      email: "ada@example.test",
      href: "/account/security?email=ada%40example.test",
    });
  });

  test("an invite link does not offer a request form", () => {
    expect(
      mapAuthLinkError({
        search: "?error=access_denied&error_code=otp_expired&type=invite",
        hash: "",
        pathname: "/auth/recovery",
      }),
    ).toEqual({ problem: "expired", kind: "invite" });
  });

  test("a hash can name the flow when the query only names the failure", () => {
    expect(
      mapAuthLinkError({
        search: "?error=access_denied",
        hash: "#type=invite",
        pathname: "/auth/recovery",
      }),
    ).toEqual({ problem: "expired", kind: "invite" });
  });

  test("other failures and unknown flows stay on the page that received them", () => {
    expect(
      mapAuthLinkError({
        search: "?error=server_error",
        hash: "",
        pathname: "/auth/recovery",
      }),
    ).toBeNull();
    expect(
      mapAuthLinkError({
        search: "",
        hash: "",
        pathname: "/auth/recovery",
      }),
    ).toBeNull();
    expect(
      mapAuthLinkError({
        search: "?error=access_denied&error_code=otp_expired",
        hash: "",
        pathname: "/chat",
      }),
    ).toBeNull();
  });
});

describe("authLinkErrorRedirect", () => {
  test("sends an expired recovery link to the shared screen and names the flow", () => {
    const target = authLinkErrorRedirect({
      origin,
      pathname: "/auth/recovery",
      searchParams: new URLSearchParams("error=access_denied&error_code=otp_expired"),
    });
    expect(target?.pathname).toBe("/auth/link-error");
    expect(target?.searchParams.get("error")).toBe("access_denied");
    expect(target?.searchParams.get("error_code")).toBe("otp_expired");
    expect(target?.searchParams.get("type")).toBe("recovery");
  });

  test("an unknown type on recovery still opens the link screen as recovery", () => {
    const target = authLinkErrorRedirect({
      origin,
      pathname: "/auth/recovery",
      searchParams: new URLSearchParams("error=access_denied&error_code=otp_expired&type=not-a-flow"),
    });
    expect(target?.pathname).toBe("/auth/link-error");
    expect(target?.searchParams.get("type")).toBe("recovery");
    expect(target?.searchParams.get("error")).toBe("access_denied");
    expect(
      mapAuthLinkError({
        search: target?.search ?? "",
        hash: "",
        pathname: "/auth/link-error",
      }),
    ).toEqual({
      problem: "expired",
      kind: "request",
      flow: "recovery",
      email: null,
      href: "/auth/forgot-password",
    });
  });

  test("a named invite on the recovery path is not replaced", () => {
    const target = authLinkErrorRedirect({
      origin,
      pathname: "/auth/recovery",
      searchParams: new URLSearchParams("error=access_denied&type=invite"),
    });
    expect(target?.searchParams.get("type")).toBe("invite");
  });

  test("does not redirect a screen that is already the shared one or the confirm route's own", () => {
    expect(
      authLinkErrorRedirect({
        origin,
        pathname: "/auth/link-error",
        searchParams: new URLSearchParams("error=access_denied&type=recovery"),
      }),
    ).toBeNull();
    expect(
      authLinkErrorRedirect({
        origin,
        pathname: "/auth/confirm/error",
        searchParams: new URLSearchParams("error_code=otp_expired&type=recovery&ref=c0ffee00"),
      }),
    ).toBeNull();
  });
});

describe("rendersOwnLinkError", () => {
  test("the shared screen and the confirm error page keep their own view and reference", () => {
    expect(rendersOwnLinkError("/auth/link-error")).toBe(true);
    expect(rendersOwnLinkError("/auth/confirm/error")).toBe(true);
    expect(rendersOwnLinkError("/auth/recovery")).toBe(false);
    expect(rendersOwnLinkError("/")).toBe(false);
  });
});

describe("notFoundHref", () => {
  test("signed in goes home and signed out goes to login", () => {
    expect(notFoundHref(true, "/chat")).toBe("/chat");
    expect(notFoundHref(false, "/chat")).toBe("/?auth=login");
  });
});

describe("prefilledEmail", () => {
  test("keeps a single address and drops anything else", () => {
    expect(prefilledEmail("ada@example.test")).toBe("ada@example.test");
    expect(prefilledEmail(" ada@example.test ")).toBe("ada@example.test");
    expect(prefilledEmail("not an email")).toBe("");
    expect(prefilledEmail(null)).toBe("");
    expect(prefilledEmail("a\r\nb@x.com")).toBe("");
    expect(prefilledEmail("a\nb@x.com")).toBe("");
    expect(prefilledEmail("a\tb@x.com")).toBe("");
    expect(prefilledEmail("a b@x.com")).toBe("");
  });
});

describe("confirmErrorView", () => {
  test("a used or expired recovery link asks for a new one", () => {
    expect(confirmErrorView("?error_code=otp_expired&type=recovery&ref=c0ffee00")).toEqual({
      problem: "expired",
      kind: "request",
      flow: "recovery",
      email: null,
      href: "/auth/forgot-password",
    });
  });

  test("a link missing a part says so and keeps the invite exit", () => {
    expect(confirmErrorView("?error_code=malformed_link&type=invite")).toEqual({ problem: "malformed", kind: "invite" });
  });

  test("any other refusal is not called expired", () => {
    expect(confirmErrorView("?error_code=verify_failed&type=email_change")).toEqual({
      problem: "rejected",
      kind: "request",
      flow: "email_change",
      email: null,
      href: "/account/security",
    });
    expect(confirmErrorView("?type=signup")).toMatchObject({ problem: "rejected", kind: "request", flow: "recovery" });
    expect(confirmErrorView("")).toMatchObject({ problem: "rejected", kind: "request", flow: "recovery" });
  });

  test("the logged reference is read back only when it is a plain id", () => {
    expect(confirmReference("?error_code=otp_expired&ref=c0ffee00")).toBe("c0ffee00");
    expect(confirmReference("?ref=<script>")).toBeNull();
    expect(confirmReference("?error_code=otp_expired")).toBeNull();
  });
});
