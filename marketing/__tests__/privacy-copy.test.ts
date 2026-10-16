import { describe, expect, test } from "bun:test";
import { businessContent } from "../components/content";
import { privacyCopy } from "../components/privacy-copy";
import { businessContactEmail } from "../components/site-copy";
import { LOCALES } from "../lib/site-routes";

// The privacy text names the services that actually touch visitor data. When a
// service is added or replaced, this list and the text change together.
const PROCESSORS = ["Render", "Resend", "Apple", "Supabase", "Cloudflare"] as const;

const sectionText = (section: { paragraphs?: string[]; items?: string[] }) =>
  [...(section.paragraphs ?? []), ...(section.items ?? [])].join("\n");

describe.each(["en"] as const)("privacy text (%s)", (locale) => {
  const copy = privacyCopy[locale];
  const byId = (id: string) => {
    const section = copy.sections.find((candidate) => candidate.id === id);
    if (!section) throw new Error(`missing section ${id}`);
    return section;
  };
  const providers = byId("providers").items ?? [];
  const allText = JSON.stringify(copy);

  test.each(PROCESSORS)("names %s once, in the providers section", (name) => {
    expect(providers.filter((item) => item.includes(name))).toHaveLength(1);
    const elsewhere = copy.sections
      .filter((section) => section.id !== "providers")
      .map(sectionText)
      .join("\n");
    expect(elsewhere).not.toContain(name);
  });

  test("mentions iCloud Mail once, beside the public address", () => {
    expect(allText.match(/iCloud/g)).toHaveLength(1);
    expect(providers.some((item) => item.includes("iCloud Mail") && item.includes(businessContactEmail))).toBe(true);
  });

  // Held until the founder confirms Cuadrao LLC is formed and operates the site.
  // The prepared wording is in docs/runbooks/cuadrao-marketing-launch.md.
  test("does not publish an operator before it is confirmed", () => {
    expect(copy.sections.some((section) => section.id === "operator")).toBe(false);
    expect(allText).not.toMatch(/LLC|Garcés|Garces|Lucas/);
  });

  test("does not claim data is received only in certain cases", () => {
    expect(allText).not.toMatch(/solo cuando|only when/i);
  });

  test("keeps the hosting IP-address disclosure", () => {
    expect(sectionText(byId("data"))).toMatch(/IP/);
  });

  test("does not describe the mailbox vaguely", () => {
    expect(allText).not.toContain("buzón de Cuadrao");
    expect(allText).not.toContain("Cuadrao's mailbox");
  });

  test("tells the visitor the site briefly keeps their address and email to limit submissions", () => {
    const data = sectionText(byId("data"));
    expect(data).toMatch(locale === "es" ? /memoria del servidor/ : /server's memory/);
    expect(data).toMatch(locale === "es" ? /dos horas/ : /two hours/);
  });

  test("does not claim the contact details are used only to reply", () => {
    expect(sectionText(byId("data"))).not.toMatch(/solo para responderte|only to reply/);
  });
});

// The line under the contact form must say what the privacy page says: the email also
// keys a short in-memory submission limit, so it is not used "only" to reply.
describe.each(LOCALES)("contact form privacy line (%s)", (locale) => {
  test("does not claim the details are used only to reply", () => {
    expect(businessContent[locale].contact.privacy).not.toMatch(/solo para responderte|only to reply/);
  });
});

