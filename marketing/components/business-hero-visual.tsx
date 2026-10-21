import { ArrowDownRight } from "lucide-react";
import type { BusinessLocale } from "./content";
import { formatSampleMoney } from "./sample-data";
import { priorityAmount, priorityCopy, priorityName, samplePriorities } from "./sample-priorities";
import styles from "./business-hero-visual.module.css";

export function BusinessHeroVisual({ locale }: { locale: BusinessLocale }) {
  const c = priorityCopy[locale];
  const first = samplePriorities[0];
  return (
    <figure className={styles.scene}>
      <a href="#el-producto" className={styles.folio} aria-label={locale === "es" ? "Explorar los asuntos por revisar" : "Explore the items to review"}>
        <div className={styles.backPaper} aria-hidden="true" />
        <div className={styles.note}>
          <div className={styles.noteTop}><span>cuadrao</span><small>{locale === "es" ? "PARA NEGOCIOS" : "FOR BUSINESS"}</small></div>
          <div className={styles.noteTitle}><span>{locale === "es" ? "Para tener presente" : "Keep in view"}</span><span>{String(samplePriorities.length).padStart(2, "0")}</span></div>
          <div className={styles.collection}>
            <span>{c[first.kind].label}</span>
            <strong>{formatSampleMoney(priorityAmount(first), locale)}</strong>
            <p>{priorityName(first, locale)}</p>
          </div>
          <div className={styles.supporting}>
            {samplePriorities.slice(1).map((priority) => <div key={priority.id}><span>{c[priority.kind].label}</span><strong>{formatSampleMoney(priorityAmount(priority), locale)}</strong></div>)}
          </div>
          <div className={styles.noteBottom}><span>{c.count}</span><ArrowDownRight size={20} aria-hidden="true" /></div>
        </div>
        <span className={styles.folioMark} aria-hidden="true">cuadrao</span>
      </a>
      <figcaption>{c.preview}</figcaption>
    </figure>
  );
}
