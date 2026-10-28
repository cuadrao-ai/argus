import { useTranslation } from "react-i18next";
import styles from "./invoicing-preview.module.css";

const BLOCKS = ["payments", "corrections", "delivery"] as const;

export default function InvoiceUnavailableBlocks() {
  const { t } = useTranslation();
  return <section className={styles.footer} data-testid="invoice-unavailable-blocks"><dl className={styles.facts}>{BLOCKS.map(block => <div key={block}><dt>{t(`business.invoicing.block_${block}`)}</dt><dd>{t(`business.invoicing.block_${block}_unavailable`)}</dd></div>)}</dl></section>;
}
