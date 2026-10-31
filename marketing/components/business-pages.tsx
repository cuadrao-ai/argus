import Image from "next/image";
import { ArrowUpRight } from "lucide-react";
import type { BusinessLocale } from "./content";
import { businessContactEmail, siteCopy } from "./site-copy";
import { BusinessHeader } from "./business-header";
import { ContactForm } from "./contact-form";
import { PersonalEarlyAccess } from "./personal-early-access";
import { BusinessFooter } from "./business-footer";
import styles from "./business.module.css";
import touchup from "./touchup.module.css";
import { TouchupLanding } from "./touchup-landing";
import { touchupCopy } from "./touchup-copy";

function FounderIdentity({ locale }: { locale: BusinessLocale }) {
  return (
    <div className={styles.founderIdentity}>
      <Image
        className={styles.founderPortrait}
        src="/cuadrao-site/lucas-garces.png"
        alt={
          locale === "es"
            ? "Retrato de Lucas Garcés"
            : "Portrait of Lucas Garcés"
        }
        width={96}
        height={96}
        sizes="96px"
      />
      <Image
        className={styles.founderSignature}
        src="/cuadrao-site/lucas-garces-signature.png"
        alt="Lucas Garcés"
        width={1942}
        height={809}
        sizes="200px"
      />
    </div>
  );
}

export function BusinessLanding({ locale }: { locale: BusinessLocale }) {
  const c = siteCopy[locale];
  return (
    <div
      className={`${styles.site} ${touchup.site}`}
      lang={locale === "es" ? "es-DO" : "en"}
      id="top"
      data-page-background="business"
    >
      <BusinessHeader locale={locale} />
      <main id="business-main" tabIndex={-1}>
        <TouchupLanding locale={locale} />
        <section
          className={styles.approach}
          id="como-funciona"
          aria-labelledby="approach-title"
        >
          <div className={styles.approachHeading}>
            <div>
              <h2 id="approach-title">{c.approachTitle}</h2>
            </div>
            <p>{c.approachBody}</p>
          </div>
          <ol className={`${styles.steps} ${touchup.pilotRail}`}>
            {c.steps.map((item) => (
              <li key={item.title}>
                <span aria-hidden="true" className={touchup.railDot} />
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </li>
            ))}
          </ol>
        </section>
        <section
          className={`${styles.founder} ${styles.founderLetter}`}
          id="nosotros"
          aria-labelledby="founder-title"
        >
          <div>
            <h2 id="founder-title">{c.founderTitle}</h2>
          </div>
          <div className={styles.founderStory}>
            <p className={styles.salutation}>
              {locale === "es" ? "Hola," : "Hello,"}
            </p>
            {c.founderParagraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
            <p className={styles.letterSignoff}>
              {locale === "es" ? "Gracias por leer," : "Thank you for reading,"}
            </p>
            <FounderIdentity locale={locale} />
          </div>
        </section>
        <section
          className={styles.faq}
          id="preguntas"
          aria-labelledby="faq-title"
        >
          <div className={styles.faqHeading}>
            <p className={styles.sectionIndex}>{c.faqLink}</p>
            <h2 id="faq-title">{c.faqTitle}</h2>
            <p>{c.faqBody}</p>
          </div>
          <div className={styles.faqItems}>
            {[
              {
                question: touchupCopy[locale].limitsQuestion,
                answer: touchupCopy[locale].limitsAnswer,
              },
              {
                question: touchupCopy[locale].fitQuestion,
                answer: touchupCopy[locale].fitAnswer,
              },
              ...c.faq.slice(2),
            ].map((item) => (
              <details key={item.question}>
                <summary>
                  {item.question}
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>
      <BusinessFooter locale={locale} business />
    </div>
  );
}

export function ContactPage({ locale }: { locale: BusinessLocale }) {
  const c = siteCopy[locale];
  return (
    <div
      className={`${styles.site} ${touchup.site}`}
      lang={locale === "es" ? "es-DO" : "en"}
      id="top"
      data-page-background="business"
      data-page="contact"
    >
      <BusinessHeader locale={locale} page="contact" />
      <main id="business-main" tabIndex={-1} className={styles.demoLayout}>
        <section className={styles.demoIntro}>
          <h1>{c.contactLead}</h1>
          <p>{c.contactBody}</p>
          <p className={styles.contactPrivacy}>{c.contactNote}</p>
        </section>
        <ContactForm locale={locale} />
        <aside className={styles.contactDetails} aria-label={c.contact}>
          <div className={styles.directContact}>
            <p>{c.emailInvitation}</p>
            <a
              className={styles.textAction}
              href={`mailto:${businessContactEmail}`}
            >
              {businessContactEmail}
              <ArrowUpRight size={18} aria-hidden="true" />
            </a>
            <small>{c.emailHelp}</small>
          </div>
          <div className={styles.contactPerson}>
            <FounderIdentity locale={locale} />
            <p>{c.founderNote}</p>
          </div>
        </aside>
      </main>
      <BusinessFooter locale={locale} showClosing={false} business />
    </div>
  );
}

export function PersonalPage({ locale }: { locale: BusinessLocale }) {
  return (
    <div
      className={`${styles.site} ${styles.personalSite} ${touchup.site}`}
      lang={locale === "es" ? "es-DO" : "en"}
      id="top"
      data-page-background="personal"
    >
      <BusinessHeader locale={locale} page="personal" />
      <main id="business-main" tabIndex={-1}>
        <PersonalEarlyAccess locale={locale} />
      </main>
      <BusinessFooter locale={locale} showClosing={false} personal />
    </div>
  );
}
