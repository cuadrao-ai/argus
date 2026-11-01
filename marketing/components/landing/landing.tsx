import { ArrowDown, ArrowUpRight } from "lucide-react";
import { businessPath } from "@/lib/site-routes";
import { BusinessFooter } from "../business-footer";
import { BusinessHeader } from "../business-header";
import business from "../business.module.css";
import { RotatingUseCase } from "../rotating-use-case";
import { siteCopy } from "../site-copy";
import touchup from "../touchup.module.css";
import { landingCopy, type LandingLocale } from "./landing-copy";
import styles from "./landing.module.css";
import { ProductScene } from "./product-scene";

export function Landing({ locale }: { locale: LandingLocale }) {
  const copy = landingCopy[locale];
  const site = siteCopy[locale];
  return (
    <div
      className={`${business.site} ${touchup.site}`}
      lang="es-DO"
      id="top"
      data-page-background="business"
    >
      <BusinessHeader locale={locale} plain />
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
              {copy.howLink}
              <ArrowDown size={16} aria-hidden="true" />
            </a>
          </div>
        </section>
        <ProductScene locale={locale} />
      </main>
      <BusinessFooter locale={locale} />
    </div>
  );
}
