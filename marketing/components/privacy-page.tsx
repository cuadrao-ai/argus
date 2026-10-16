import { ArrowUpRight } from "lucide-react";
import { BusinessHeader } from "./business-header";
import { BusinessFooter } from "./business-footer";
import { privacyCopy } from "./privacy-copy";
import { htmlLang } from "@/lib/site-routes";
import { businessContactEmail } from "./site-copy";
import styles from "./business.module.css";
import privacyStyles from "./privacy.module.css";

export function PrivacyPage({ locale }: { locale: "en" }) {
  const copy = privacyCopy[locale];
  return (
    <div className={styles.site} lang={htmlLang(locale)} id="top">
      <BusinessHeader locale={locale} page="privacy" />
      <main id="business-main" tabIndex={-1} className={privacyStyles.layout}>
        <header className={privacyStyles.intro}>
          <span className={styles.sectionIndex}>{copy.eyebrow}</span>
          <h1>{copy.title}</h1>
          <p>{copy.intro}</p>
          <small>{copy.updated}</small>
        </header>
        <div className={privacyStyles.sections}>
          {copy.sections.map((section) => (
            <section key={section.id} id={section.id} className={privacyStyles.section}>
              <h2>{section.title}</h2>
              {section.paragraphs?.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
              {section.items && (
                <ul>
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </section>
          ))}
          <a className={styles.textAction} href={`mailto:${businessContactEmail}`}>
            {businessContactEmail}
            <ArrowUpRight size={18} aria-hidden="true" />
          </a>
        </div>
      </main>
      <BusinessFooter locale={locale} showClosing={false} business />
    </div>
  );
}
