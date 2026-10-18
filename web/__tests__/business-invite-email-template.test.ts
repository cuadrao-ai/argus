import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "bun:test";
import { renderBusinessInviteEmail } from "../../marketing/lib/email/business-invite";

const data = { ownerName: "Lucía", businessName: "Colmado", expiresDate: "24 de octubre de 2026", signInUrl: "https://app.example.test/" };
test("invite HTML and plain text match the canonical Python artifact snapshots", () => {
  const result = renderBusinessInviteEmail(data);
  const folder = new URL("../../tests/business/invite_email_snapshots/", import.meta.url);
  assert.equal(result.html, readFileSync(new URL("invite.html", folder), "utf8"));
  assert.equal(result.text, readFileSync(new URL("invite.txt", folder), "utf8"));
  assert.equal(result.subject, "Lucía te invitó a Colmado en Cuadrao");
  assert.ok(result.html.includes("Entra con este correo para aceptar. Vence el 24 de octubre de 2026."));
  assert.ok(result.html.includes("Saludos,<br>Cuadrao"));
});

test("the button cannot contain an accept token and template values cannot inject HTML", () => {
  assert.throws(() => renderBusinessInviteEmail({ ...data, signInUrl: "https://app.example.test/?token=abc" }));
  assert.throws(() => renderBusinessInviteEmail({ ...data, ownerName: "Name\r\nBcc: person@example.test" }));
  const result = renderBusinessInviteEmail({ ...data, businessName: "<script>alert(1)</script>" });
  assert.ok(!result.html.includes("<script>"));
  assert.ok(result.html.includes("&lt;script&gt;"));
  assert.ok(result.text.includes("<script>alert(1)</script>"));
});
