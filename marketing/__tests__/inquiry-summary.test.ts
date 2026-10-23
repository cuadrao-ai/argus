import { describe, expect, test } from "bun:test";
import {
  EMPTY_PROFILE,
  NOTE_MAX,
  PHONE_MAX,
  SOURCE_MAX,
  buildInquiryMessage,
} from "../components/inquiry-summary";

describe("inquiry message", () => {
  test("an untouched form sends only what the visitor typed", () => {
    expect(buildInquiryMessage(EMPTY_PROFILE, "  Hola  ")).toBe("Hola");
    expect(buildInquiryMessage(EMPTY_PROFILE, "")).toBe("");
  });

  test("answers lead the note, in Spanish for the founder", () => {
    const message = buildInquiryMessage(
      {
        role: "accountant",
        channel: "whatsapp",
        phone: " +1 809 555 0123 ",
        source: "mi contador",
        pilot: true,
      },
      "Tengo 12 clientes.",
    );
    expect(message).toBe(
      [
        "Soy: contador/a",
        "Prefiere: WhatsApp +1 809 555 0123",
        "Nos conoció por: mi contador",
        "Demostración: le interesa una demostración de Cuadrao",
        "",
        "Tengo 12 clientes.",
      ].join("\n"),
    );
    expect(message).not.toMatch(/piloto|prototipo|prototype|probar|try it/i);
  });

  test("an unchecked demo request adds no demo line", () => {
    const message = buildInquiryMessage({ ...EMPTY_PROFILE, pilot: false }, "Consulta.");
    expect(message).toBe("Consulta.");
    expect(message).not.toMatch(/demostración|piloto|probar/i);
  });

  test("a phone number is dropped unless WhatsApp is chosen", () => {
    expect(
      buildInquiryMessage({ ...EMPTY_PROFILE, channel: "email", phone: "123" }, ""),
    ).toBe("Prefiere: correo");
  });

  test("the fullest message fits the server limit of 1000 characters", () => {
    const message = buildInquiryMessage(
      {
        role: "owner",
        channel: "whatsapp",
        phone: "9".repeat(PHONE_MAX),
        source: "s".repeat(SOURCE_MAX),
        pilot: true,
      },
      "x".repeat(NOTE_MAX),
    );
    expect(message.length).toBeLessThanOrEqual(1000);
  });
});
