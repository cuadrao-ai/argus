import { Monitor, Smartphone } from "lucide-react";
import type { BusinessLocale } from "./content";
import styles from "./owner-stories.module.css";

export function BusinessSurfaces({ locale }: { locale: BusinessLocale }) {
  return <section className={styles.surfaces} aria-label={locale === "es" ? "Cuadrao en web y móvil" : "Cuadrao on web and mobile"}>
    <div><Monitor size={27} strokeWidth={1.4} aria-hidden="true" /><h3>{locale === "es" ? "El negocio completo, en la web." : "The full business workspace, on the web."}</h3><p>{locale === "es" ? "Revisar cuentas, planear, trabajar con clientes y preparar reportes por período. Un espacio de trabajo para seguir los detalles con calma." : "Review accounts, plan, work with customers and prepare period reports. A workspace for following the details."}</p><small>{locale === "es" ? "Espacio web previsto" : "Planned web workspace"}</small></div>
    <div><Smartphone size={27} strokeWidth={1.4} aria-hidden="true" /><h3>{locale === "es" ? "Lo necesario, cuando estás fuera." : "The essentials, when you are away."}</h3><p>{locale === "es" ? "Capturar un documento, revisar una propuesta rápida y ver dónde está tu dinero. El móvil acompaña al espacio web." : "Capture a document, review a quick proposal and check where your money stands. Mobile accompanies the web workspace."}</p><small>{locale === "es" ? "Acompañante móvil previsto" : "Planned mobile companion"}</small></div>
  </section>;
}
