import { expect, test } from "bun:test";
import { matchesRecordSearch } from "@/components/business-app/transacciones/records-search-preview";

const fields = { name: "Estación Ruta 3", note: "Pago de José", documents: ["B0100000042", "factura-octubre.pdf"] };
test("records search covers names, current notes and document references", () => {
  for (const query of [" estacion ", "JOSE", "0000042", "OCTUBRE.PDF", ""]) expect(matchesRecordSearch(query, fields)).toBe(true);
  for (const query of ["DOP", "2100", "aprobado"]) expect(matchesRecordSearch(query, fields)).toBe(false);
  expect(matchesRecordSearch("Jose", { ...fields, note: "Reemplazada" })).toBe(false);
  expect(matchesRecordSearch("anything", { name: null, note: "", documents: [] })).toBe(false);
});
