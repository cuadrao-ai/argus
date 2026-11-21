import assert from "node:assert/strict";
import { test } from "bun:test";
import { defaultReceptionPreferences } from "@/components/business-app/recepcion/reception-columns";
import { receptionGrid, SELECT_COLUMN_PX } from "@/components/business-app/recepcion/reception-grid";

type Variables = Record<"--columns" | "--laptop-columns" | "--compact-columns", string>;
const grid = (tab: { select: boolean; status: boolean }, sender: boolean) => receptionGrid({ ...defaultReceptionPreferences(), hidden: sender ? ["amount", "currency"] : ["sender", "amount", "currency"] }, tab, "120px") as unknown as Variables;
const tracks = (columns: string) => columns.match(/minmax\([^)]*\)|\S+/g)!;
const TODOS = { select: false, status: true };
const LISTOS = { select: true, status: false };

test("Bandeja owns the 80px Moneda track at every table width", () => {
  const preferences = { ...defaultReceptionPreferences(), hidden: ["file", "source", "sender", "amount", "status", "arrival"] };
  const columns = receptionGrid(preferences, TODOS, "120px") as unknown as Variables;
  for (const width of ["--columns", "--laptop-columns", "--compact-columns"] as const) {
    assert.equal(tracks(columns[width])[1], "80px");
  }
});

for (const sender of [false, true]) for (const width of ["--columns", "--laptop-columns", "--compact-columns"] as const) {
  test(`${width}, Enviado por ${sender ? "on" : "off"}: moving to Listos drops Estado and leaves Contenido and every other track as they were`, () => {
    const [content, ...todos] = tracks(grid(TODOS, sender)[width]);
    const [box, sameContent, ...listos] = tracks(grid(LISTOS, sender)[width]);
    assert.equal(box, `${SELECT_COLUMN_PX}px`);
    assert.equal(sameContent, content);
    const status = todos.findIndex(track => track.startsWith("minmax"));
    assert.deepEqual(listos, todos.filter((_, index) => index !== status), "every other track keeps its width");
  });
}

test("Enviado por on adds its own fixed track from the laptop width up", () => {
  for (const width of ["--columns", "--laptop-columns"] as const) assert.equal(tracks(grid(TODOS, true)[width]).length, tracks(grid(TODOS, false)[width]).length + 1);
  assert.equal(tracks(grid(TODOS, true)["--compact-columns"]).length, tracks(grid(TODOS, false)["--compact-columns"]).length, "below 940px Canal and Enviado por share one column");
});

test("the tracks follow the person's order: the box and Contenido stay first and the action track last, by position", () => {
  const moved = { ...defaultReceptionPreferences(), order: ["arrival", "status", "file", "source", "sender", "amount", "currency"], hidden: ["sender", "amount", "currency"] };
  const columns = (receptionGrid(moved, LISTOS, "120px") as unknown as Variables)["--columns"];
  assert.deepEqual(tracks(columns), [`${SELECT_COLUMN_PX}px`, "minmax(200px, 360px)", "126px", "104px", "150px", "minmax(140px, 1fr)"]);
});

test("below 940px Canal and Enviado por share the place of whichever comes first", () => {
  const moved = { ...defaultReceptionPreferences(), order: ["status", "sender", "file", "source", "amount", "currency", "arrival"], hidden: ["amount", "currency"] };
  const columns = (receptionGrid(moved, TODOS, "120px") as unknown as Variables)["--compact-columns"];
  assert.deepEqual(tracks(columns), ["minmax(180px, 360px)", "minmax(160px, 240px)", "150px", "76px", "106px", "minmax(140px, 1fr)"]);
});
