import { ArrowDown, ArrowUpRight, FileText } from "lucide-react";
import type { BusinessLocale } from "./content";
import { businessPath } from "@/lib/site-routes";
import { siteCopy } from "./site-copy";
import { touchupCopy } from "./touchup-copy";
import { CaptureStory } from "./capture-story";
import { RotatingUseCase } from "./rotating-use-case";
import styles from "./touchup.module.css";

export function TouchupLanding({ locale }: { locale: BusinessLocale }) {
  const c = touchupCopy[locale];
  const original = siteCopy[locale];
  return (
    <>
      <section
        className={`${styles.section} ${styles.hero}`}
        aria-labelledby="business-title"
      >
        <div className={styles.heroCopy}>
          <h1 id="business-title">
            {original.title[0]}
            <br />
            {original.title[1]}
          </h1>
          <RotatingUseCase phrases={c.useCases} />
          <p className={styles.lead}>{c.description}</p>
          <div className={styles.actions}>
            <a className={styles.cta} href={businessPath("es", "contact")}>
              {original.cta}
              <ArrowUpRight size={18} aria-hidden="true" />
            </a>
            <a className={styles.textLink} href="#el-producto">
              {original.explore}
              <ArrowDown size={16} aria-hidden="true" />
            </a>
          </div>
        </div>
        <div className={styles.scene}>
          <div className={styles.heroCard}>
            <div className={styles.cardTop}>
              <FileText size={22} aria-hidden="true" />
              <span>{c.steps[0].label}</span>
            </div>
            <p>{c.steps[0].detail}</p>
            <strong className={styles.heroAmount}>{c.steps[0].amount}</strong>
            <span className={styles.status}>{c.steps[0].status}</span>
            <div className={styles.paperLines} aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
            <small>{original.note}</small>
          </div>
        </div>
      </section>
      <div id="el-producto">
        <CaptureStory locale={locale} />
      </div>
      <section
        className={`${styles.section} ${styles.soft}`}
        aria-labelledby="principles-title"
      >
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>{c.principlesLabel}</p>
          <h2 id="principles-title">{c.principlesTitle}</h2>
          <p>{c.principlesBody}</p>
        </div>
        <div className={styles.four}>
          {c.principles.map((item) => (
            <article key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
