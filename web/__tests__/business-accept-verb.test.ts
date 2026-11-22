import assert from "node:assert/strict";
import { test } from "bun:test";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

type Tree = { [key: string]: string | Tree };

const BUSINESS_COPY = /^(business|business_access|workspace_setup_preview)\.|^settings\.whatsapp\./;
/** A review marker, not copy a person reads. */
const MARKER = /\.copy_review$/;

function leaves(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string" ? [[path, value] as [string, string]] : leaves(value, path);
  });
}

const copy = (tree: unknown) => leaves(tree as Tree).filter(([key]) => BUSINESS_COPY.test(key) && !MARKER.test(key));

test("the owner accepts a document: no Business text says aprobar or approve", () => {
  assert.ok(copy(spanish).length > 1000 && copy(english).length > 1000, "the Business strings were found");
  assert.deepEqual(copy(spanish).filter(([, value]) => /apr(ob|ueb)/i.test(value)), []);
  assert.deepEqual(copy(english).filter(([, value]) => /approv/i.test(value)), []);
});

test("the accept action and its result use the one verb", () => {
  const es = new Map(copy(spanish));
  const en = new Map(copy(english));
  assert.equal(es.get("business.dossier.approve_action"), "Aceptar");
  assert.equal(es.get("business.dossier.approve_next"), "Aceptar y siguiente");
  assert.equal(es.get("business.dossier.confirm.accept_anyway"), "Aceptar de todos modos");
  assert.equal(es.get("business.history.approved"), "Aceptado");
  assert.equal(en.get("business.dossier.approve_next"), "Accept and next");
  assert.equal(en.get("business.dossier.confirm.accept_anyway"), "Accept anyway");
  assert.equal(en.get("business.history.approved"), "Accepted");
});
