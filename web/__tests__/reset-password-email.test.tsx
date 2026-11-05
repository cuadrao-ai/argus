import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import assert from "node:assert/strict";
import { test } from "bun:test";
import { renderResetPasswordEmail } from "../server/emails/reset-password";

test("recovery preserves its verification URL and Spanish safety copy in the shared layout", async () => {
  const url = `https://app.example.test/auth/confirm?token_hash=${"a".repeat(64)}&type=recovery&next=%2Fauth%2Frecovery`;
  const email = await renderResetPasswordEmail(url, 3600);
  assert.equal(email.subject, "Cambio de contraseña en Cuadrao");
  for (const copy of ["Recibimos una solicitud para cambiar tu contraseña de Cuadrao. Puedes hacerlo desde este enlace:", "Cambiar mi contraseña", "El enlace vence en 1 hora y solo se puede usar una vez.", "Si no fuiste tú, ignora este correo. Tu contraseña sigue igual.", "hola@cuadrao.ai"]) {
    assert.ok(email.html.includes(copy));
    assert.ok(email.text.includes(copy));
  }
  assert.ok(email.html.includes("Saludos,<br>Cuadrao"));
  assert.ok(email.text.includes("Saludos,\nCuadrao"));
  assert.ok(email.text.split("\n").includes(url));
  assert.ok(!email.text.includes(`${url}.`));
  assert.ok(!email.text.includes("supabase.co"));
  assert.ok(email.html.includes(url.replaceAll("&", "&amp;")));
  assert.ok(!email.html.includes("Salir de la lista"));
  assert.ok(!email.html.includes('<p class="code"'));
});
