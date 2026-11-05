import { BriefcaseBusiness, FilePenLine, UserPlus } from "lucide-react";
import { useInvoiceWords } from "./InvoiceDocument";
import styles from "./invoicing-preview.module.css";

export default function InvoiceSetupCards({ disabled, onBusiness, onCustomer, onInvoice }: { disabled: boolean; onBusiness: () => void; onCustomer: () => void; onInvoice: () => void }) {
  const { word } = useInvoiceWords();
  const cards = [
    { key: "setup_business", icon: BriefcaseBusiness, action: onBusiness, guarded: false },
    { key: "setup_customer", icon: UserPlus, action: onCustomer, guarded: true },
    { key: "setup_invoice", icon: FilePenLine, action: onInvoice, guarded: true },
  ];
  return <div className={styles.setupCards} data-testid="invoice-setup-cards">{cards.map(({ key, icon: Icon, action, guarded }) => <button key={key} type="button" className={styles.setupCard} disabled={guarded && disabled} onClick={action}>
    <Icon size={21} aria-hidden="true" />
    <strong>{word(key)}</strong>
    <span>{word(`${key}_help`)}</span>
  </button>)}</div>;
}
