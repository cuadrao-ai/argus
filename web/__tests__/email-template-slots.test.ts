import { expect, test } from "bun:test";
import { renderAccountEmail } from "../server/emails/account-layout.generated";
import { EMAIL_TEMPLATE_SLOTS, renderTemplateSlot } from "../../marketing/lib/email/template-slots";

test("title and optional preheader escape HTML while plain text preserves copy", () => {
  const email = renderAccountEmail({ title: 'A < B & "C"', preheader: '<preview>&', paragraphs: ['Body'] });
  expect(email.html).toContain('<title>A &lt; B &amp; &quot;C&quot;</title>');
  expect(email.html).toContain('&lt;preview&gt;&amp;</div>');
  expect(email.html).not.toContain('<preview>');
  expect(email.text).toStartWith('A < B & "C"');
  expect(email.text).not.toContain('<preview>');
  expect(renderAccountEmail({title: 'Title', paragraphs: []}).html).not.toContain('class="preheader"');
});

test("asset origins are configurable and reject paths, credentials and unsafe schemes", () => {
  const email = renderAccountEmail({title: 'Title', paragraphs: []}, {assetOrigin: 'https://assets.example.test'});
  expect(email.html).toContain('https://assets.example.test/email/wordmark-light.png');
  expect(email.html).not.toContain('onrender.com');
  for (const assetOrigin of ['http://example.test', 'https://user@example.test', 'https://example.test/path', 'https://example.test/?x=1', 'https://example.test/\r\nx']) {
    expect(() => renderAccountEmail({title: 'Title', paragraphs: []}, {assetOrigin})).toThrow();
  }
});

test("all thirteen empty slots refuse delivery and share the preview layout", () => {
  expect(Object.keys(EMAIL_TEMPLATE_SLOTS)).toHaveLength(13);
  for (const slot of Object.keys(EMAIL_TEMPLATE_SLOTS) as Array<keyof typeof EMAIL_TEMPLATE_SLOTS>) {
    expect(EMAIL_TEMPLATE_SLOTS[slot].status).toBe('awaiting_copy');
    expect(() => renderTemplateSlot(slot)).toThrow('awaiting approved copy');
    const preview = renderTemplateSlot(slot, {preview: true});
    expect(preview.html).toContain('alt="Cuadrao"');
    expect(preview.text).not.toContain('undefined');
    expect(preview.subject).toBe('');
    expect(preview.sendable).toBe(false);
  }
});
