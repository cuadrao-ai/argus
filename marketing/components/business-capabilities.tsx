import { ArrowDown, CalendarDays, Search, Users, Wallet } from "lucide-react";
import type { BusinessLocale } from "./content";
import styles from "./business-stories.module.css";
import ownerStyles from "./owner-stories.module.css";

const capabilities = [
  { icon: Wallet, href: "#el-producto", es: ["Entender tu dinero", "Cuentas, ingresos, gastos y deudas."], en: ["Understand your money", "Accounts, income, expenses and debt."] },
  { icon: CalendarDays, href: "#planificar", es: ["Planear lo que sigue", "Presupuestos, metas y próximos pagos."], en: ["Plan what comes next", "Budgets, goals and upcoming payments."] },
  { icon: Search, href: "#registrar-encontrar", es: ["Registrar y resolver", "Captura, asistente, búsqueda y avisos."], en: ["Record and resolve", "Capture, assistant, search and updates."] },
  { icon: Users, href: "#la-idea", es: ["Seguir clientes y cobros", "Ventas, abonos y saldos pendientes."], en: ["Follow customers and payments", "Sales, partial payments and balances."] },
] as const;

export function BusinessCapabilities({ locale }: { locale: BusinessLocale }) {
  return <section className={styles.capabilities} aria-labelledby="capabilities-title">
    <div className={styles.capabilityHeading}>
      <h2 id="capabilities-title">{locale === "es" ? "Entiende tu dinero. Planea tu próximo paso." : "Understand your money. Plan your next move."}</h2>
      <p>{locale === "es" ? "Tus cuentas, planes y trabajo diario, en un mismo lugar. Explora lo que estamos preparando." : "Your accounts, plans and daily work, in one place. Explore what we are preparing."}</p>
    </div>
    <nav className={styles.capabilityLinks} aria-label={locale === "es" ? "Explora los ejemplos del producto" : "Explore the product examples"}>
      {capabilities.map(({ icon: Icon, href, ...copy }) => <a href={href} key={href}><Icon size={22} strokeWidth={1.4} aria-hidden="true" /><span><strong>{copy[locale][0]}</strong><small>{copy[locale][1]}</small></span><ArrowDown size={16} aria-hidden="true" /></a>)}
    </nav>
    <p className={ownerStyles.availability}>{locale === "es" ? "Producto en desarrollo. Los ejemplos usan datos ficticios y muestran funciones previstas. El alcance de cada piloto se acordará contigo." : "Product in development. Examples use fictional data and show planned features. We will agree on each pilot’s scope with you."}</p>
  </section>;
}
