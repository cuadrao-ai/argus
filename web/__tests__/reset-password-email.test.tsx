import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { renderResetPasswordEmail } from "../server/emails/reset-password";

const recoveryUrl = "https://skedzwocnmrhfigiwyzi.supabase.co/auth/v1/verify?token=synthetic-token&type=recovery&redirect_to=https%3A%2F%2Fcuadrao-web-staging.onrender.com%2Fauth%2Frecovery";
const paragraphs = [
  "Hola:",
  "Recibimos una solicitud para cambiar la contraseña de tu cuenta de Cuadrao.",
  "El enlace vence en 1 hora y solo se puede usar una vez.",
  "Si no pediste este cambio, ignora este correo. Tu contraseña sigue igual.",
  "¿Tienes dudas? Responde a este correo.",
  "Saludos,",
  "Cuadrao",
];

describe("Cuadrao password recovery email", () => {
  test("renders approved Spanish copy and the same recovery link in HTML and generated plain text", async () => {
    const email = await renderResetPasswordEmail(recoveryUrl);
    assert.equal(email.subject, "Restablece tu contraseña de Cuadrao");
    for (const paragraph of paragraphs) {
      assert.ok((email.html).includes(paragraph));
      assert.ok((email.text).includes(paragraph));
    }
    assert.ok((email.text).includes("Crear nueva contraseña"));
    assert.ok((email.text).includes(recoveryUrl));
    assert.ok((email.html).includes(recoveryUrl.replaceAll("&", "&amp;")));
    assert.ok((email.html).includes('lang="es"'));
    assert.ok((email.html).includes('alt="Cuadrao"'));
    assert.ok((email.html).includes("/icons/cuadrao-192.png"));
    assert.ok((email.html).includes("#172b26"));
    assert.ok((email.html).includes("#fafbf8"));
    assert.ok((email.html).includes('content="light dark"'));
    assert.ok((email.html).includes("prefers-color-scheme: dark"));
    assert.ok((email.html).includes("[data-ogsc] .cuadrao-button"));
    assert.ok((email.html).includes("background-color: #b6e87a !important; color: #172b26 !important;"));
    assert.equal(email.text.trim().endsWith("Cuadrao LLC"), true);
    assert.ok((email.html).includes("Crea una nueva contraseña para tu cuenta."));
    assert.ok(!(email.html).includes("FOOTER_ADDRESS"));
    assert.ok(!(email.html).includes("unsubscribe"));
  });
});
