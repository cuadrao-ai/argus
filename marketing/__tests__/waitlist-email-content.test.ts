import { expect, test } from "bun:test";
import { unsubscribeHeaders, WAITLIST_BUSINESS_LINE, WAITLIST_EMAILS } from "../lib/waitlist/email-content";

test("the four templates contain the approved personal-app copy", () => {
  expect(Object.keys(WAITLIST_EMAILS)).toEqual(["confirmation", "reminder", "welcome", "launch"]);
  expect(WAITLIST_EMAILS.confirmation.subject).toBe("Confirma tu lugar en la lista de la app personal de Cuadrao");
  expect(WAITLIST_EMAILS.reminder.subject).toBe("¿Sigues interesado? Confirma tu lugar en Cuadrao");
  expect(WAITLIST_EMAILS.welcome.subject).toBe("Ya estás en la lista de la app personal de Cuadrao");
  expect(WAITLIST_EMAILS.confirmation.paragraphs).toEqual(["Recibimos tu solicitud para la lista de espera de la app personal de Cuadrao, para llevar tus gastos y los de tu hogar. Confirma tu correo para que te avisemos cuando esté lista para ti."]);
  expect(WAITLIST_EMAILS.reminder.paragraphs).toEqual(WAITLIST_EMAILS.confirmation.paragraphs);
  expect(WAITLIST_EMAILS.confirmation.button).toBe("Confirmar mi correo");
  expect(WAITLIST_EMAILS.confirmation.expiryNote).toBe("Este enlace vence en 48 horas.");
  expect(WAITLIST_EMAILS.launch.automatic).toBe(false);
  expect(WAITLIST_BUSINESS_LINE).toBe("¿Buscas Cuadrao para tu negocio? Es un servicio aparte. Escríbenos en cuadrao.ai/contacto.");
  expect(JSON.stringify(WAITLIST_EMAILS)).not.toContain("code");
});

test("one-click unsubscribe headers reject header injection", () => {
  expect(unsubscribeHeaders("https://cuadrao.example.test/api/waitlist/leave?token=opaque")).toEqual({
    "List-Unsubscribe": "<https://cuadrao.example.test/api/waitlist/leave?token=opaque>",
    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
  });
  expect(() => unsubscribeHeaders("http://cuadrao.example.test/leave")).toThrow();
  expect(() => unsubscribeHeaders("https://cuadrao.example.test/leave\r\nX-Foo: yes")).toThrow();
});
