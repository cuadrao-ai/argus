import { afterEach, describe, expect, test } from "bun:test";
import { NextRequest } from "next/server";
import { proxy } from "../proxy";

const previousIndexing = process.env.CUADRAO_SITE_INDEXING;

afterEach(() => {
  if (previousIndexing === undefined) delete process.env.CUADRAO_SITE_INDEXING;
  else process.env.CUADRAO_SITE_INDEXING = previousIndexing;
});

function robotsHeader(path: string): string | null {
  return proxy(new NextRequest(`http://127.0.0.1${path}`)).headers.get("x-robots-tag");
}

describe("private-host robots header", () => {
  test("privacy and deletion pages omit it, including one trailing slash", () => {
    delete process.env.CUADRAO_SITE_INDEXING;

    expect(robotsHeader("/eliminar-datos")).toBeNull();
    expect(robotsHeader("/eliminar-datos/")).toBeNull();
    expect(robotsHeader("/privacidad")).toBeNull();
    expect(robotsHeader("/privacidad/")).toBeNull();
  });

  test("every other page still sends noindex, nofollow", () => {
    delete process.env.CUADRAO_SITE_INDEXING;

    expect(robotsHeader("/")).toBe("noindex, nofollow");
    expect(robotsHeader("/terminos")).toBe("noindex, nofollow");
    expect(robotsHeader("/en/privacy")).toBe("noindex, nofollow");
    expect(robotsHeader("/en/delete-data")).toBe("noindex, nofollow");
    expect(robotsHeader("/eliminar-datos/extra")).toBe("noindex, nofollow");
    expect(robotsHeader("/privacidad/extra")).toBe("noindex, nofollow");
  });

  test("a public host sends no robots header", () => {
    process.env.CUADRAO_SITE_INDEXING = "public";

    expect(robotsHeader("/terminos")).toBeNull();
    expect(robotsHeader("/privacidad")).toBeNull();
  });
});
