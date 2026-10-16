import { businessContactEmail } from "./site-copy";

type Section = { id: string; title: string; paragraphs?: string[]; items?: string[] };

type PrivacyCopy = {
  eyebrow: string;
  title: string;
  intro: string;
  updated: string;
  sections: Section[];
};

const email = businessContactEmail;

const en: PrivacyCopy = {
  eyebrow: "PRIVACY",
  title: "Your privacy at Cuadrao.",
  intro:
    "We use the data you share to answer your inquiries and to tell you when early access is available. This page explains what information we receive, how we use it and how you can ask us to delete it.",
  updated: "Updated October 8, 2026",
  sections: [
    {
      id: "data",
      title: "What data we receive",
      paragraphs: [
        "If you write to us: your name, your email, the optional comment, the page language and, if you share it, your WhatsApp number. We use them to reply to you.",
        "If you request Cuadrao Personal early access: your email, the page language, the signup date and the version of this text you accepted. We use them only to tell you when access is available. Signing up does not create an account or guarantee immediate access.",
        "When you visit the site: the hosting provider may record technical connection data, such as the IP address.",
        "To slow down automated submissions, the site keeps your IP address and, if you write to us, your email in the server's memory, not in a database. They are forgotten after at most two hours, or sooner if the service restarts.",
      ],
    },
    {
      id: "not-used",
      title: "What we do not use",
      paragraphs: [
        "This site does not use cookies, analytics tools or advertising tracking, and it does not store data in your browser. Fonts are served from the site itself. We do not use your contact details to send you advertising.",
        "Please do not enter documents, account numbers or private financial information in the form.",
      ],
    },
    {
      id: "providers",
      title: "Providers involved",
      items: [
        "Render hosts the site.",
        "Resend sends the form messages by email and, later, the early-access notice. It may keep its own sending logs.",
        `Apple (iCloud Mail) receives and stores the email sent to ${email}, including form messages and removal requests.`,
        "Supabase stores early-access signups on servers in the United States (Ohio).",
        "Cloudflare manages the cuadrao.ai domain.",
      ],
    },
    {
      id: "retention",
      title: "How long we keep it",
      paragraphs: [
        "Your message is kept in our email for as long as it is needed to reply and follow up.",
        "Your early-access signup stays until you ask to remove it. When you remove it we delete your email and keep a technical fingerprint of the address, not the address itself, along with the language and the signup, notice and removal dates, so we do not register or email you again.",
        "Technical connection records are kept by the hosting provider under its own rules.",
      ],
    },
    {
      id: "choices",
      title: "Your choices and contact",
      paragraphs: [
        `You can ask us to show, correct or delete your data, or to remove your signup, by writing to ${email}. We handle these requests by hand.`,
      ],
    },
  ],
};

export const privacyCopy: Record<"en", PrivacyCopy> = { en };
