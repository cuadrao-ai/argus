import Image from "next/image";
import { ArrowUpRight, Instagram, Music2, Youtube } from "lucide-react";
import { SOCIAL_PLATFORMS, socialPreviewEnabled, visibleSocials } from "@/lib/social";
import { businessPath } from "@/lib/site-routes";
import { businessContent, type BusinessLocale } from "./content";
import { businessContactEmail, siteCopy } from "./site-copy";
import styles from "./business.module.css";
import shell from "./touchup-shell.module.css";

export function ContactLink({
  locale,
  light = false,
}: {
  locale: BusinessLocale;
  light?: boolean;
}) {
  return (
    <a
      className={`${styles.button} ${light ? styles.buttonLight : ""}`}
      href={businessPath(locale, "contact")}
    >
      {siteCopy[locale].cta}
      <ArrowUpRight size={19} aria-hidden="true" />
    </a>
  );
}

type FooterCopy = (typeof siteCopy)[BusinessLocale];

function LegalNav({ locale, c }: { locale: BusinessLocale; c: FooterCopy }) {
  return (
    <nav aria-label={c.footerLegal}>
      <span>{c.footerLegal}</span>
      <a href={businessPath(locale, "privacy")}>{c.privacyLabel}</a>
      {locale === "es" ? <a href={businessPath(locale, "terms")}>{c.terms}</a> : <span className={styles.footerPending}>{c.terms}</span>}
      {locale === "es" ? <a href={businessPath(locale, "deletion")}>Eliminar tus datos</a> : <span className={styles.footerPending}>{c.responsible}</span>}
    </nav>
  );
}

const SOCIAL_ICONS = { tiktok: Music2, instagram: Instagram, youtube: Youtube } as const;

function FooterBar({ c }: { c: FooterCopy }) {
  const socials = visibleSocials(
    SOCIAL_PLATFORMS,
    socialPreviewEnabled(process.env.CUADRAO_SOCIAL_PREVIEW),
  );
  return (
    <div className={styles.footerBar}>
      <p>Cuadrao LLC · 1209 Mountain Road Pl NE Ste N, Albuquerque, NM 87110</p>
      {socials.length > 0 && (
        <div className={styles.footerSocial} role="group" aria-label={c.socialLabel}>
          {socials.map(({ id, label, href }) => {
            const Icon = SOCIAL_ICONS[id];
            return href ? (
              <a key={id} href={href} target="_blank" rel="noopener noreferrer" aria-label={label}>
                <Icon size={18} aria-hidden="true" />
              </a>
            ) : (
              <span key={id} role="img" aria-label={label}>
                <Icon size={18} aria-hidden="true" />
              </span>
            );
          })}
        </div>
      )}
      <a href="#top" className={styles.backTop}>
        {c.top}
        <ArrowUpRight size={16} aria-hidden="true" />
      </a>
    </div>
  );
}

export function BusinessFooter({
  locale,
  showClosing = true,
  business = false,
  personal = false,
}: {
  locale: BusinessLocale;
  showClosing?: boolean;
  business?: boolean;
  personal?: boolean;
}) {
  const c = siteCopy[locale];
  return (
    <footer
      className={`${styles.footer} ${business ? styles.businessFooter : ""} ${shell.footer}`}
    >
      {showClosing && (
        <section className={styles.closing} aria-labelledby="closing-title">
          <div>
            <h2 id="closing-title">{c.closingTitle}</h2>
          </div>
          <div>
            <p>{c.closingBody}</p>
            <ContactLink locale={locale} />
          </div>
        </section>
      )}
      {business ? (
        <div className={styles.businessFooterGrid}>
          <div className={styles.footerIdentity}>
            <a href={businessPath(locale)} className={shell.footerBrand}>
              <Image src="/cuadrao-site/cuadrao-lockup-dark.svg" width={268} height={56} alt="cuadrao" />
            </a>
            <span>{c.business}</span>
            <p>{c.footerTag}</p>
          </div>
          <nav aria-label={c.footerExplore}>
            <span>{c.footerExplore}</span>
            <a href={`${businessPath(locale)}#el-producto`}>{c.business}</a>
            <a href={`${businessPath(locale)}#la-idea`}>{c.explore}</a>
            <a href={`${businessPath(locale)}#preguntas`}>{c.faqLink}</a>
            <a href={businessPath(locale, "personal")}>{c.personal}</a>
          </nav>
          <nav aria-label={c.footerTalk}>
            <span>{c.footerTalk}</span>
            <a href={`${businessPath(locale)}#nosotros`}>{c.about}</a>
            <a href={businessPath(locale, "contact")}>{c.contact}</a>
            <a href={`mailto:${businessContactEmail}`}>{businessContactEmail}</a>
            <a
              href="https://www.linkedin.com/in/lucasgarces"
              target="_blank"
              rel="noopener noreferrer"
            >
              Lucas · LinkedIn <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          </nav>
          <LegalNav locale={locale} c={c} />
          <FooterBar c={c} />
        </div>
      ) : (
        <div className={`${styles.businessFooterGrid} ${styles.lightFooterGrid}`}>
          <div className={styles.footerIdentity}>
            <a
              href={businessPath(locale, personal ? "personal" : "home")}
              className={shell.footerBrand}
            >
              <Image src="/cuadrao-site/cuadrao-lockup-light.svg" width={268} height={56} alt="cuadrao" />
            </a>
            <span>{personal ? c.personal : c.business}</span>
            <p>
              {personal
                ? locale === "es"
                  ? "Tus finanzas, en orden."
                  : "Your finances, in order."
                : c.footerTag}
            </p>
            <small>
              {personal
                ? locale === "es"
                  ? "Cuadrao Personal · acceso anticipado"
                  : "Cuadrao Personal · early access"
                : c.footerLocal}
            </small>
          </div>
          <nav aria-label={businessContent[locale].closing.footerLabel}>
            <span>{c.footerExplore}</span>
            <a href={businessPath(locale)}>{c.business}</a>
            <a href={businessPath(locale, "personal")}>{c.personal}</a>
          </nav>
          <nav aria-label={c.footerTalk}>
            <span>{c.footerTalk}</span>
            {personal ? (
              <a href={`${businessPath(locale, "personal")}#early-access`}>
                {locale === "es" ? "Acceso anticipado" : "Early access"}
              </a>
            ) : (
              <a href={businessPath(locale, "contact")}>{c.contact}</a>
            )}
            <a href={`mailto:${businessContactEmail}`}>{businessContactEmail}</a>
          </nav>
          <LegalNav locale={locale} c={c} />
          <FooterBar c={c} />
        </div>
      )}
      <div className={styles.wordmarkCrop} aria-hidden="true">
        <span>cuadrao</span>
      </div>
    </footer>
  );
}
