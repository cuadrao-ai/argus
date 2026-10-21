import { describe, expect, test } from "bun:test";

import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";

describe("the sample source answers like the new search contract", () => {
  test("a query pages one list by cursor and leaves the others empty", async () => {
    const source = createFixtureBusinessDataSource();
    const first = await source.search("cliente");
    expect(first.ventas.length).toBe(5);
    expect(first.next_cursors.ventas).toBe("offset:5");
    const next = await source.searchMore!("cliente", "ventas", first.next_cursors.ventas!);
    expect(next.ventas.length).toBe(2);
    expect(next.next_cursors.ventas).toBeNull();
    expect([next.expenses, next.receipts, next.email_deliveries]).toEqual([[], [], []]);
    expect(new Set([...first.ventas, ...next.ventas].map((item) => item.id)).size).toBe(7);
  });

  test("emails and senders are searchable, and a made-up cursor is refused with the invalid-cursor code", async () => {
    const source = createFixtureBusinessDataSource();
    const found = await source.search("ferreteria");
    expect(found.email_deliveries.map((item) => item.id)).toEqual(["email-ferreteria"]);
    expect(found.email_senders.map((item) => item.value)).toEqual(["ventas@ferreterialaesquina.example"]);
    const refused = await source.searchMore!("ferreteria", "expenses", "nope").catch((error) => error);
    expect((refused as { code: string }).code).toBe("business_search_invalid_cursor");
  });

  test("an opened result ranks first, and recents repeat once, newest first, until removed or cleared", async () => {
    const source = createFixtureBusinessDataSource();
    await source.recordSearchOpen!("ventas", "venta-4");
    expect((await source.search("cliente")).ventas[0].id).toBe("venta-4");
    await source.addSearchRecent!("uno");
    await source.addSearchRecent!("dos");
    await source.addSearchRecent!("UNO");
    const recents = await source.searchRecents!();
    expect(recents.map((item) => item.q)).toEqual(["UNO", "dos"]);
    await source.removeSearchRecent!(recents[0].id);
    expect((await source.searchRecents!()).map((item) => item.q)).toEqual(["dos"]);
    await source.clearSearchRecents!();
    expect(await source.searchRecents!()).toEqual([]);
  });
});
