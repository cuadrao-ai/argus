import { describe, test, expect } from "bun:test";
import {
  DEFAULT_APPEARANCE,
  readAppearance,
  saveAppearance,
  parseAppearance,
  validateImageFile,
  imageGeometry,
  type IdentityAppearance,
} from "@/lib/identity-appearance";
import {
  createLocalBusiness,
  readLocalBusinesses,
  withLocalBusinessPreview,
  LOCAL_BUSINESS_PREFIX,
} from "@/app/design-workspace/localBusinessPreview";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import type { BusinessDataSource } from "@/components/business-app/business-data";
function memory() {
  const entries = new Map<string, string>();
  return {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => {
      entries.set(key, value);
    },
    removeItem: (key: string) => {
      entries.delete(key);
    },
  };
}
const avatar: IdentityAppearance = {
  kind: "avatar",
  token: "teal",
  mark: "initials",
};
describe("local identity and business ownership", () => {
  test("identity save and remove are scoped and rejected writes preserve saved appearance", () => {
    const store = memory();
    saveAppearance(store, "business:a", avatar);
    saveAppearance(store, "person:a", {
      kind: "avatar",
      token: "gold",
      mark: "icon",
    });
    expect(readAppearance(store, "business:a")).toEqual(avatar);
    expect(readAppearance(store, "business:b")).toEqual(DEFAULT_APPEARANCE);
    expect(() =>
      saveAppearance(
        {
          ...store,
          setItem: () => {
            throw new Error("quota");
          },
        },
        "business:a",
        DEFAULT_APPEARANCE,
      ),
    ).toThrow();
    expect(readAppearance(store, "business:a")).toEqual(avatar);
    saveAppearance(store, "business:a", DEFAULT_APPEARANCE);
    expect(readAppearance(store, "business:a")).toEqual(DEFAULT_APPEARANCE);
    expect(readAppearance(store, "person:a").kind).toBe("avatar");
  });
  test("untrusted image sources and oversized files cannot enter saved identity", () => {
    expect(
      parseAppearance({
        kind: "image",
        source: "https://outside.example/image.png",
      }),
    ).toEqual(DEFAULT_APPEARANCE);
    expect(validateImageFile({ type: "image/svg+xml", size: 100 })).toBe(
      "file_type",
    );
    expect(
      validateImageFile({ type: "image/png", size: 11 * 1024 * 1024 }),
    ).toBe("file_size");
    expect(validateImageFile({ type: "image/webp", size: 1024 })).toBeNull();
  });
  test("fit keeps the original aspect and fill centers the square crop", () => {
    expect(
      imageGeometry(400, 200, { mode: "fit", zoom: 1, x: 0, y: 0 }),
    ).toEqual({ width: 256, height: 128, left: 0, top: 64 });
    expect(
      imageGeometry(400, 200, { mode: "fill", zoom: 1, x: 0, y: 0 }),
    ).toEqual({ width: 512, height: 256, left: -128, top: 0 });
  });
  test("creation needs explicit country and name, persists once, and keeps separate identities", () => {
    const store = memory();
    expect(() => createLocalBusiness(store, "La Palma", "", avatar)).toThrow();
    expect(() => createLocalBusiness(store, " ", "DO", avatar)).toThrow();
    const id = LOCAL_BUSINESS_PREFIX + "test";
    createLocalBusiness(store, "  Taller Nuevo  ", "DO", avatar, id);
    createLocalBusiness(store, "duplicate", "DO", avatar, id);
    expect(readLocalBusinesses(store)).toEqual([
      { id, name: "Taller Nuevo", country: "DO" },
    ]);
    expect(readAppearance(store, `business:${id}`)).toEqual(avatar);
  });
  test("local businesses start empty and never call the underlying business source", async () => {
    const store = memory(),
      id = LOCAL_BUSINESS_PREFIX + "empty";
    createLocalBusiness(store, "Taller", "CA", DEFAULT_APPEARANCE, id);
    let leaked = 0;
    const fixture = createFixtureBusinessDataSource();
    const base: BusinessDataSource = {
      ...fixture,
      receiptPage: undefined,
      receiptActivity: undefined,
      searchMore: undefined,
      spaces: async () => [
        {
          space_id: "original",
          grant_id: "original",
          name: "Original",
          role: "owner",
          capabilities: ["read"],
          access_seen: true,
        },
      ],
      workspace: async () => {
        leaked++;
        throw new Error("leak");
      },
      receipt: async () => {
        leaked++;
        throw new Error("leak");
      },
      uploadReceipt: async () => {
        leaked++;
        throw new Error("leak");
      },
    };
    const source = withLocalBusinessPreview(
      base,
      () => store,
      () => id,
    );
    expect((await source.spaces()).map((item) => item.grant_id)).toEqual([
      "original",
      id,
    ]);
    expect(await source.receiptPage!("inbox")).toMatchObject({ items: [] });
    expect((await source.workspace()).accounts).toEqual([]);
    expect((await source.workspace()).country).toBe("CA");
    expect(await source.receipts("inbox")).toEqual([]);
    expect(await source.expenses("2026-01-01", null)).toEqual([]);
    expect(await source.access()).toEqual({ grants: [], invites: [] });
    expect(await source.emailDeliveries()).toEqual([]);
    expect((await source.emailIntake()).receiving_address).not.toContain(
      "7f3a9c21",
    );
    await expect(source.receipt("old-receipt")).rejects.toThrow(
      "local_action_unavailable",
    );
    await expect(
      source.uploadReceipt(new File(["x"], "x.png"), false, "id"),
    ).rejects.toThrow("local_action_unavailable");
    expect(leaked).toBe(0);
  });
});
