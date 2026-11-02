import assert from "node:assert/strict";
import { test } from "bun:test";
import { defaultReceptionPreferences } from "@/components/business-app/recepcion/ReceptionControls";
import { receptionGrid, SELECT_COLUMN_PX } from "@/components/business-app/recepcion/reception-grid";

type Variables = Record<"--columns" | "--laptop-columns" | "--compact-columns", string>;
const grid = (tab: { select: boolean; status: boolean }, sender: boolean) => receptionGrid({ ...defaultReceptionPreferences(), sender }, tab, "120px", 80) as unknown as Variables;
const tracks = (columns: string) => columns.match(/minmax\([^)]*\)|\S+/g)!;
const TODOS = { select: false, status: true };
const LISTOS = { select: true, status: false };

for (const sender of [false, true]) for (const width of ["--columns", "--laptop-columns", "--compact-columns"] as const) {
  test(`${width}, Remitente ${sender ? "on" : "off"}: moving to Listos changes only Contenido's share`, () => {
    const [content, ...todos] = tracks(grid(TODOS, sender)[width]);
    const [box, sameContent, ...listos] = tracks(grid(LISTOS, sender)[width]);
    assert.equal(box, `${SELECT_COLUMN_PX}px`);
    assert.equal(sameContent, content);
    const status = todos.findIndex(track => track.startsWith("minmax"));
    assert.deepEqual(listos, todos.filter((_, index) => index !== status), "every other track keeps its width");
  });
}

test("Remitente on adds its own fixed track from the laptop width up", () => {
  for (const width of ["--columns", "--laptop-columns"] as const) assert.equal(tracks(grid(TODOS, true)[width]).length, tracks(grid(TODOS, false)[width]).length + 1);
  assert.equal(tracks(grid(TODOS, true)["--compact-columns"]).length, tracks(grid(TODOS, false)["--compact-columns"]).length, "below 940px Canal and Remitente share one column");
});
