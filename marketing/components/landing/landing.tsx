import { ArrowDown, ArrowUpRight } from "lucide-react";
import { businessPath, htmlLang } from "@/lib/site-routes";
import { BusinessFooter } from "../business-footer";
import { BusinessHeader } from "../business-header";
import { FounderIdentity } from "../business-pages";
import business from "../business.module.css";
import { RotatingUseCase } from "../rotating-use-case";
import { siteCopy } from "../site-copy";
import touchup from "../touchup.module.css";
import { AccountantSection } from "./accountant-section";
import { FaqList } from "./faq-list";
import { HowItWorks } from "./how-it-works";
import { landingCopy, type LandingLocale } from "./landing-copy";
import styles from "./landing.module.css";
import { ProblemCards } from "./problem-cards";
import { ProductScene } from "./product-scene";

export function Landing({ locale }: { locale: LandingLocale }) {
  const copy = landingCopy[locale];
  const site = siteCopy[locale];
  return (
    <div
      className={`${business.site} ${touchup.site} ${styles.landing}`}
      lang={htmlLang(locale)}
      id="top"
      data-page-background="business"
    >
      <BusinessHeader locale={locale} />
      <main id="business-main" tabIndex={-1}>
        <section className={styles.hero} aria-labelledby="landing-title">
          <h1 id="landing-title">
            {site.title[0]}
            <br />
            {site.title[1]}
          </h1>
          <RotatingUseCase phrases={copy.useCases} className={styles.useLine} />
          <p className={styles.lead}>{copy.lead}</p>
          <div className={styles.actions}>
            <a className={touchup.cta} href={businessPath(locale, "contact")}>
              {site.cta}
              <ArrowUpRight size={18} aria-hidden="true" />
            </a>
            <a className={touchup.textLink} href="#como">
              {site.explore}
              <ArrowDown size={16} aria-hidden="true" />
            </a>
          </div>
        </section>
        <ProductScene locale={locale} />
        <ProblemCards locale={locale} />
        <HowItWorks locale={locale} />
        <AccountantSection locale={locale} />
        <section className={styles.letter} id="nosotros" aria-labelledby="landing-founder-title">
          <h2 id="landing-founder-title">{site.founderTitle}</h2>
          <p className={styles.hello}>{copy.letter.hello}</p>
          {site.founderParagraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          <p>{copy.letter.thanks}</p>
          <FounderIdentity locale={locale} />
        </section>
        <section className={styles.faq} id="preguntas" aria-labelledby="landing-faq-title">
          <div className={styles.faqHeading}>
            <h2 id="landing-faq-title">{site.faqTitle}</h2>
            <p>{site.faqBody}</p>
          </div>
          <FaqList items={site.faq} />
        </section>
      </main>
      <BusinessFooter locale={locale} />
    </div>
  );
}
