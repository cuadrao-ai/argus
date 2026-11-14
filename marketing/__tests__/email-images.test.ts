import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderAccountEmail } from "../lib/email/account-layout";

const folder = join(import.meta.dir, "..", "public", "email");
const pixels = (name: string) => {
  const png = readFileSync(join(folder, name));
  return [png.readUInt32BE(16), png.readUInt32BE(20)];
};

describe("email header images", () => {
  test("the header image is exported at twice the size the layout states", () => {
    const { html } = renderAccountEmail({ title: "Título", paragraphs: [] }, { assetOrigin: "https://assets.example.test" });
    const images = [...html.matchAll(/<img [^>]*>/g)].map(([tag]) => tag);
    expect(images).toHaveLength(1);
    const [, file, width, height] = images[0].match(/src="https:\/\/assets\.example\.test\/email\/([^"]+)" alt="Cuadrao" width="(\d+)" height="(\d+)"/)!;
    expect(file).toBe("lockup-dark.png");
    expect(pixels(file)).toEqual([Number(width) * 2, Number(height) * 2]);
  });

  test("templates published with the wordmark header still load their images into the 168 by 36 slot", () => {
    for (const name of ["wordmark-light.png", "wordmark-dark.png"]) {
      expect(pixels(name)).toEqual([168 * 3, 36 * 3]);
    }
  });
});
