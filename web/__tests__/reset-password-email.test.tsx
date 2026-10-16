import assert from "node:assert/strict";
import { test } from "bun:test";
import { renderResetPasswordEmail } from "../server/emails/reset-password";

test("recovery preserves its verification URL and Spanish safety copy in the shared layout", async () => {
  const url = "https://skedzwocnmrhfigiwyzi.supabase.co/auth/v1/verify?token=synthetic&type=recovery";
  const email = await renderResetPasswordEmail(url);
  assert.equal(email.subject, "Cambia tu contraseña de Cuadrao");
  for (const copy of ["Pediste cambiar tu contraseña.", "Hazlo aquí", "El enlace vence en 1 hora y solo se puede usar una vez.", "Si no fuiste tú, ignora este correo. Tu contraseña sigue igual.", "Saludos, el equipo de Cuadrao", "hola@cuadrao.ai"]) {
    assert.ok(email.html.includes(copy));
    assert.ok(email.text.includes(copy));
  }
  assert.ok(email.text.includes(url));
  assert.ok(email.html.includes(url.replaceAll("&", "&amp;")));
  assert.ok(!email.html.includes("Salir de la lista"));
  assert.ok(!email.html.includes('<p class="code"'));
});
