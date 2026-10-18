import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { emailPalette as p, renderAccountEmail } from "../server/emails/account-layout.generated";

const link = "https://example.test/confirm?token=synthetic&next=%2Fbiz";
const luminance = (color: string) => {
  const channels = color.slice(1).match(/../g)!.map((value) => parseInt(value, 16) / 255)
    .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
};

describe("shared account email layout", () => {
  test("escapes copy and renders the same action in a button, grey fallback and plain text", () => {
    const result = renderAccountEmail({title: '<img src="x">', paragraphs: ["<script>&'"], action: {label: "Entrar", url: link}});
    expect(result.html).toContain("&lt;script&gt;&amp;&#39;");
    expect(result.html).not.toContain('<img src="x">');
    expect(result.html).toContain('width="560"');
    expect(result.html).toContain("border-radius:12px");
    expect(result.html).toContain('content="light dark"');
    expect(result.html).toContain("prefers-color-scheme:dark");
    expect(result.html).toContain("[data-ogsc] .button");
    expect(result.html).toContain('alt="Cuadrao"');
    expect(result.html).toContain("v:roundrect");
    expect(result.html).toContain("min-height:48px");
    expect(result.html).toContain("overflow-wrap:anywhere");
    expect(result.text).toContain(link);
    expect(result.text).toContain("Saludos,\nCuadrao");
    expect(result.text).toContain("¿Necesitas ayuda? Escríbenos a hola@cuadrao.ai");
    expect(result.html).not.toMatch(/width="1"|tracking|unsubscribe/);
  });
  test("keeps signup codes unbroken and rejects codes in waitlist messages", () => {
    const rendered = renderAccountEmail({title: "Tu código", paragraphs: [], code: "55070219", expiryNote: "Vence en 60 minutos."});
    expect(rendered.html).toContain('white-space:nowrap">55070219</p>');
    expect(rendered.html).toContain("letter-spacing:4px");
    expect(() => renderAccountEmail({title: "x", paragraphs: [], code: "5507 0219"})).toThrow();
    // @ts-expect-error A waitlist message cannot contain an account code.
    expect(() => renderAccountEmail({title: "x", paragraphs: [], code: "55070219", unsubscribeUrl: link})).toThrow();
  });
  test("waitlist leave link is in the footer and shares the help text style", () => {
    const rendered = renderAccountEmail({title: "Lista", paragraphs: [], action: {label: "Confirmar mi correo", url: link}, expiryNote: "Este enlace vence en 48 horas.", unsubscribeUrl: link});
    expect(rendered.html.indexOf("Salir de la lista")).toBeGreaterThan(rendered.html.indexOf("hola@cuadrao.ai"));
    expect(rendered.html).not.toContain('<p class="code"');
    expect(rendered.text).toContain("Este enlace vence en 48 horas.");
  });
  test("waitlist mail uses the configured legal address and account mail stays Cuadrao LLC", () => {
    const address = "Cuadrao LLC, 1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU.";
    const rendered = renderAccountEmail({title: "Lista", paragraphs: [], unsubscribeUrl: link, postalAddress: address});
    expect(rendered.text).toContain(address);
    expect(rendered.html).toContain(address);
    expect(rendered.html.indexOf(address)).toBeGreaterThan(rendered.html.indexOf("hola@cuadrao.ai"));
    for (const postalAddress of [address, address.replace("Cuadrao LLC, ", "")]) {
      const account = renderAccountEmail({title: "Cuenta", paragraphs: []}, {postalAddress});
      expect(account.text).toContain("Cuadrao LLC");
      expect(account.text).not.toContain("1209 Mountain");
      expect(account.html).not.toContain("1209 Mountain");
      expect(account.text.match(/Cuadrao LLC/g)).toHaveLength(1);
      expect(account.html).not.toContain("Salir de la lista");
    }
  });
  test("rejects script, credential and header-injection URLs", () => {
    for (const url of ["javascript:alert(1)", "https://user:pass@example.test", "https://example.test/\r\nx"]) {
      expect(() => renderAccountEmail({title: "x", paragraphs: [], action: {label: "x", url}})).toThrow();
      expect(() => renderAccountEmail({title: "x", paragraphs: [], unsubscribeUrl: url})).toThrow();
    }
  });
  test("all visible text and background pairs pass AA in both modes", () => {
    for (const [foreground, background] of [[p.text,p.card],[p.muted,p.card],[p.text,p.grey],[p.text,p.tint],[p.card,p.text],[p.darkText,p.darkCard],[p.darkMuted,p.darkCard],[p.darkText,p.darkGrey],[p.darkText,p.darkTint],[p.darkAccent,p.darkCard],[p.text,p.darkAccent]]) {
      const pair = [luminance(foreground),luminance(background)].sort((a,b)=>b-a);
      expect((pair[0]+0.05)/(pair[1]+0.05)).toBeGreaterThanOrEqual(4.5);
    }
  });
  test("the deployed web copy derives exactly from the canonical marketing renderer", () => {
    const canonical = readFileSync(new URL("../../marketing/lib/email/account-layout.ts", import.meta.url),"utf8");
    const deployed = readFileSync(new URL("../server/emails/account-layout.generated.ts", import.meta.url),"utf8");
    expect(deployed.slice(deployed.indexOf("\n")+1)).toBe(canonical);
  });
});


test("account mail renders Cuadrao LLC and ignores a supplied postal address", () => {
  delete process.env.MARKETING_POSTAL_ADDRESS;
  const street = "1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU.";
  for (const postalAddress of [undefined, street, `Cuadrao LLC, ${street}`]) {
    const rendered = renderAccountEmail({title: "Cuenta", paragraphs: []}, postalAddress ? {postalAddress} : {});
    expect(rendered.html).toContain(">Cuadrao LLC</p>");
    expect(rendered.text).toContain("\n\nCuadrao LLC");
    expect(rendered.html).not.toContain("Cuadrao LLC,");
    expect(rendered.text).not.toContain(street);
    expect(rendered.html).not.toContain("Salir de la lista");
  }
});

test("unsubscribe footer fails closed without a postal address and includes it when set", () => {
  delete process.env.MARKETING_POSTAL_ADDRESS;
  const leave = "https://example.test/leave";
  const street = "1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU.";
  const address = `Cuadrao LLC, ${street}`;
  expect(() => renderAccountEmail({title: "Lista", paragraphs: [], unsubscribeUrl: leave})).toThrow("postal address");
  for (const postalAddress of ["bad\naddress", "Cuadrao LLC"]) {
    expect(() => renderAccountEmail({title: "Lista", paragraphs: [], unsubscribeUrl: leave}, {postalAddress})).toThrow("postal address");
  }
  const explicit = renderAccountEmail({title: "Lista", paragraphs: [], unsubscribeUrl: leave, postalAddress: address});
  expect(explicit.html).toContain(address);
  expect(explicit.text).toContain(address);
  process.env.MARKETING_POSTAL_ADDRESS = street;
  const fromEnv = renderAccountEmail({title: "Lista", paragraphs: [], unsubscribeUrl: leave});
  expect(fromEnv.html).toContain(address);
  expect(fromEnv.text).toContain(address);
});
