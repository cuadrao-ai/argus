import { describe, expect, test } from "bun:test";
import { businessSidebarModes } from "../lib/sidebar-mode-state";
import { identityInitials } from "../lib/sidebar-identity";

describe("Business sidebar identity and stored choices", () => {
  test("keeps each person's valid choice and rejects invalid external values", () => {
    expect(businessSidebarModes('{"owner":"collapsed","accountant":"expanded","other":"hover","invalid":true}')).toEqual({ owner: "collapsed", accountant: "expanded", other: "hover" });
    for (const input of [null, "{", "null", "[]", '"collapsed"']) expect(businessSidebarModes(input)).toEqual({});
  });
  test("uses actual identity initials without inventing a picture or business name", () => {
    expect(identityInitials("Colmado La Esquina")).toBe("CE");
    expect(identityInitials("  Ana Peña  ")).toBe("AP");
    expect(identityInitials("Ana")).toBe("A");
    expect(identityInitials(null)).toBe("·");
  });
});
