import Image from "next/image";
import { ArrowUpRight } from "lucide-react";
import type { BusinessLocale } from "./content";
import { businessContactEmail, siteCopy } from "./site-copy";
import { BusinessHeader } from "./business-header";
import { ContactForm } from "./contact-form";
import { BusinessFooter } from "./business-footer";
import styles from "./business.module.css";
import touchup from "./touchup.module.css";

export function FounderIdentity({ locale }: { locale: BusinessLocale }) {
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
      <BusinessFooter locale={locale} showClosing={false} />
    </div>
  );
}
