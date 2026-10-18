import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { renderBusinessClosedEmail } from "../../marketing/lib/email/business-closed";

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

test("Python artifact is derived from the renderer and supports single-pass literal substitutions", () => {
  const result = spawnSync('bun', ['scripts/emails/sync-business-closed.ts', '--check'], {cwd: new URL('../../', import.meta.url), encoding:'utf8'});
  expect(result.status).toBe(0);
  const artifact = JSON.parse(readFileSync(new URL('../../src/argus/domain/business/business_closed_email.generated.json', import.meta.url), 'utf8'));
  expect(artifact.schemaVersion).toBe(1);
  const replacements = new Map(Object.entries(artifact.tokens).map(([key, token]) => [token, key === 'assetOrigin' ? 'https://assets.example.test' : data[key as keyof typeof data]]));
  const pattern = new RegExp([...replacements.keys()].map(value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
  const text = artifact.text.replace(pattern, (token:string) => replacements.get(token));
  expect(text).toBe(renderBusinessClosedEmail(data).text);
  expect(text).toContain('__CUADRAO_OWNER_NAME__');
});
