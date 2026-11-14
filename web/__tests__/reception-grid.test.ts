import assert from "node:assert/strict";
import { test } from "bun:test";
import { defaultReceptionPreferences } from "@/components/business-app/recepcion/reception-columns";
import { receptionGrid, SELECT_COLUMN_PX } from "@/components/business-app/recepcion/reception-grid";

type Variables = Record<"--columns" | "--laptop-columns" | "--compact-columns", string>;
const grid = (tab: { select: boolean; status: boolean }, sender: boolean) => receptionGrid({ ...defaultReceptionPreferences(), hidden: sender ? ["amount", "currency"] : ["sender", "amount", "currency"] }, tab, "120px", 80) as unknown as Variables;
const tracks = (columns: string) => columns.match(/minmax\([^)]*\)|\S+/g)!;
const TODOS = { select: false, status: true };
const LISTOS = { select: true, status: false };

for (const sender of [false, true]) for (const width of ["--columns", "--laptop-columns", "--compact-columns"] as const) {
  test(`${width}, Remitente ${sender ? "on" : "off"}: moving to Listos drops Estado and leaves Contenido and every other track as they were`, () => {
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

test("the tracks follow the person's order: the box stays first and the action track last, by position", () => {
  const moved = { ...defaultReceptionPreferences(), order: ["arrival", "status", "file", "document", "source", "sender", "amount", "currency"], hidden: ["sender", "amount", "currency"] };
  const columns = (receptionGrid(moved, LISTOS, "120px", 80) as unknown as Variables)["--columns"];
  assert.deepEqual(tracks(columns), [`${SELECT_COLUMN_PX}px`, "126px", "104px", "minmax(200px, 360px)", "150px", "minmax(140px, 1fr)"]);
});

test("below 940px Canal and Remitente share the place of whichever comes first", () => {
  const moved = { ...defaultReceptionPreferences(), order: ["sender", "document", "file", "source", "amount", "currency", "status", "arrival"], hidden: ["amount", "currency"] };
  const columns = (receptionGrid(moved, TODOS, "120px", 80) as unknown as Variables)["--compact-columns"];
  assert.deepEqual(tracks(columns), ["150px", "minmax(180px, 360px)", "76px", "minmax(160px, 240px)", "106px", "minmax(140px, 1fr)"]);
});
