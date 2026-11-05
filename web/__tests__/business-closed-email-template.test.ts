import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { renderBusinessClosedEmail, renderBusinessLifecycleEmail } from "../../marketing/lib/email/business-closed";
import spanish from "../public/locales/es-419/common.json";
import english from "../public/locales/en/common.json";
import { assertEmailPresentation } from "./helpers/email-presentation";

const data = {businessName: 'Tienda <Río> & __CUADRAO_OWNER_NAME__', ownerName: 'A "B" <script>', closedDate: '17/10/2026', purgeDate: '16/11/2026'};

test("Business close copy preserves approved values and escapes HTML", () => {
  const result = renderBusinessClosedEmail(data, {assetOrigin: 'https://assets.example.test'});
  expect(result.subject).toBe(`${data.businessName} se cerró en Cuadrao`);
  const body = `Hola, ${data.ownerName} cerró ${data.businessName} en Cuadrao el ${data.closedDate}, y ya no tienes acceso. Si necesitas copias de los comprobantes, pídeselas a ${data.ownerName}. Si el negocio no se reabre antes del ${data.purgeDate}, sus datos se borrarán. Saludos, Cuadrao`;
  expect(result.text).toContain(body);
  expect(result.html).not.toContain('<script>');
  expect(result.html).toContain('A &quot;B&quot; &lt;script&gt;');
  expect(result.html).toContain('Tienda &lt;Río&gt; &amp; __CUADRAO_OWNER_NAME__');
  for (const value of ['', 'bad\r\nheader']) {
    expect(() => renderBusinessClosedEmail({...data,businessName:value})).toThrow();
  }
});

const ownerLink = "https://app.example.test/biz?lifecycle=manage&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756";
for (const locale of ["es-419", "en"] as const) {
  for (const kind of ["owner_closed", "purge_reminder", "member_reopened"] as const) {
    test(`${kind} renders approved ${locale} copy with one footer and a navigation link`, () => {
      const fields = {...data, businessName: "Tienda {ownerName} & <Río>", purgeTime: "22:03:07", actionUrl: kind === "member_reopened" ? "https://app.example.test/biz" : ownerLink};
      const rendered = renderBusinessLifecycleEmail({kind, ...fields}, {locale});
      const copy = (locale === "en" ? english : spanish).account_email.business_lifecycle[kind];
      const replace = (value: string) => value.replace(/\{(businessName|ownerName|closedDate|purgeDate|purgeTime)\}/g, (_, key: keyof typeof fields) => fields[key]);
      expect(rendered.subject).toBe(replace(copy.subject));
      for (const paragraph of copy.paragraphs) expect(rendered.text).toContain(replace(paragraph));
      expect(rendered.html).toContain("Tienda {ownerName} &amp; &lt;Río&gt;");
      expect(rendered.html).not.toContain("<script>");
      expect(rendered.html).toContain(copy.cta);
      expect(rendered.text).toContain(fields.actionUrl);
      expect(rendered.text.match(/\nCuadrao\n/g)).toHaveLength(1);
      expect(rendered.html).not.toContain("unsubscribe");
      expect(rendered.html).not.toContain("1209 Mountain");
      assertEmailPresentation(rendered.html, rendered.text);
      if (locale === "en") {
        expect(rendered.html).toContain('lang="en"');
        expect(rendered.text).toContain("Regards,\nCuadrao");
        expect(rendered.text).not.toContain("Saludos");
      }
    });
  }
}

test("lifecycle rendering rejects unsafe fields and links", () => {
  const fields = {kind: "owner_closed", ...data, purgeTime: "22:03:07", actionUrl: ownerLink} as const;
  for (const actionUrl of ["//outside.example.test/biz", ownerLink + "&extra=1", ownerLink + "#", ownerLink.replace("/biz", "\\biz"), ownerLink.replace("manage", "close"), ownerLink.replace("4fd88ea2-b7b4-4943-b399-664cf3bf9756", "bad"), "https://app.example.test/biz", "https://user:pass@app.example.test/biz"]) {
    expect(() => renderBusinessLifecycleEmail({...fields, actionUrl})).toThrow();
  }
  for (const businessName of ["", "bad\r\nheader", "bad\x00value", "bad\tvalue"]) {
    expect(() => renderBusinessLifecycleEmail({...fields, businessName})).toThrow();
  }
  expect(() => renderBusinessLifecycleEmail({...fields, kind: "member_reopened", actionUrl: ownerLink})).toThrow();
});

test("Python artifact is derived from the renderer and supports single-pass literal substitutions", () => {
  const result = spawnSync('bun', ['scripts/emails/sync-business-closed.ts', '--check'], {cwd: new URL('../../', import.meta.url), encoding:'utf8'});
  expect(result.status).toBe(0);
  const artifact = JSON.parse(readFileSync(new URL('../../src/argus/domain/business/business_closed_email.generated.json', import.meta.url), 'utf8'));
  expect(artifact.schemaVersion).toBe(1);
  const replacements = new Map(Object.entries(artifact.tokens).map(([key, token]) => [token, key === 'assetOrigin' ? 'https://assets.example.test' : key === 'postalAddress' ? process.env.MARKETING_POSTAL_ADDRESS : data[key as keyof typeof data]]));
  const pattern = new RegExp([...replacements.keys()].map(value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
  const text = artifact.text.replace(pattern, (token:string) => replacements.get(token));
  expect(text).toBe(renderBusinessClosedEmail(data).text);
  expect(text).toContain('__CUADRAO_OWNER_NAME__');
});
