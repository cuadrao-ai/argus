"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import type { BusinessLocale } from "./content";
import { businessContactEmail } from "./site-copy";
import styles from "./personal-early-access.module.css";
import { containsSensitiveDigits, EXPENSE_METHODS } from "@/lib/forms/personal-waitlist-input";
import { WaitlistCaptcha } from "./waitlist-captcha";
import { SignupFlight, SignupPet, usePersonalSignupScene, WelcomePhone } from "./personal-signup-scene";

type SignupState = { status: "idle" } | { status: "submitting" } | { status: "success" } | { status: "error"; message: string; rejected: boolean };

const subscribeToHydration = (): (() => void) => () => {};
const clientSnapshot = (): boolean => true;
const serverSnapshot = (): boolean => false;

const copy = {
  es: {
    eyebrow: "CUADRAO PERSONAL · ACCESO ANTICIPADO",
    title: "Tus finanzas, en orden.",
    benefit: "Tus cuentas y el próximo pago, a la vista.",
    body: "Déjanos tu correo y te avisaremos cuando puedas probar Cuadrao.",
    label: "Correo",
    button: "Avísame cuando pueda probarla",
    saving: "Guardando tu registro…",
    privacy: "Usaremos tu correo solo para avisarte sobre el acceso anticipado a Cuadrao. Para retirar tu registro, escríbenos a",
    privacyLink: "Política de privacidad",
    rateLimited: "Hiciste varios intentos seguidos. Espera unos minutos e inténtalo de nuevo.",
    success: "Revisa tu correo.",
    next: "",
    error: `No pudimos guardar tu correo. Inténtalo de nuevo o escríbenos a ${businessContactEmail}.`,
    invalid: "Revisa tu correo e inténtalo de nuevo.",
    noScript: "Activa JavaScript para usar este formulario.",
    phone: {
      alt: "Pantalla de bienvenida de Cuadrao Personal con su logo y el botón para crear una cuenta.",
      createAccount: "Crear cuenta",
      signIn: "Iniciar sesión",
    },
  },
  en: {
    eyebrow: "CUADRAO PERSONAL · EARLY ACCESS",
    title: "Your finances, in order.",
    benefit: "Your accounts and next payment, at a glance.",
    body: "Leave your email and we’ll let you know when you can try Cuadrao.",
    button: "Let me know when I can try it",
    phone: {
      alt: "Cuadrao Personal welcome screen with its logo and create-account button.",
      createAccount: "Create account",
      signIn: "Sign in",
    },
  },
} as const;

export function PersonalEarlyAccess({ locale }: { locale: BusinessLocale }) {
  const c = copy.es;
  const hydrated = useSyncExternalStore(subscribeToHydration, clientSnapshot, serverSnapshot);
  const [email, setEmail] = useState("");
  const [expenseMethod, setExpenseMethod] = useState("");
  const [wish, setWish] = useState("");
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaAttempt, setCaptchaAttempt] = useState(0);
  const [state, setState] = useState<SignupState>({ status: "idle" });
  const { rootRef, petRef, buttonRef, logoRef, flight, celebrate, finish } = usePersonalSignupScene();
  const confirmation = useRef<HTMLHeadingElement>(null);
  const pending = useRef(false);

  useEffect(() => {
    if (state.status === "success") confirmation.current?.focus({ preventScroll: true });
  }, [state.status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    const website = (event.currentTarget.elements.namedItem("website") as HTMLInputElement | null)?.value ?? "";
    setState({ status: "submitting" });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch("/api/waitlist/signups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, website, expenseMethod, wish, captchaToken }),
        signal: controller.signal,
      });
      const result: unknown = await response.json();
      if (response.ok && typeof result === "object" && result !== null && "status" in result && result.status === "registered") {
        celebrate();
        setState({ status: "success" });
      } else {
        setState({
          status: "error",
          message: response.status === 400 ? c.invalid : response.status === 429 ? c.rateLimited : c.error,
          rejected: response.status === 400,
        });
      }
    } catch {
      setState({ status: "error", message: c.error, rejected: false });
    } finally {
      clearTimeout(timeout);
      pending.current = false;
      if (locale === "es") setCaptchaAttempt((attempt) => attempt + 1);
    }
  }

  if (locale === "en") return (
    <section ref={rootRef} className={styles.hero} aria-labelledby="personal-title">
      <div className={styles.content}>
        <p className={styles.eyebrow}>{copy.en.eyebrow}</p>
        <h1 id="personal-title">{copy.en.title}</h1>
        <p className={styles.intro}>{copy.en.benefit}</p>
      </div>
      <div className={styles.capture} id="early-access">
        <p className={styles.invitation}>{copy.en.body}</p>
        <Link className={styles.redirectButton} href="/personal#early-access">{copy.en.button}<ArrowRight size={19} aria-hidden="true" /></Link>
      </div>
      <figure className={styles.preview}>
        <WelcomePhone logoRef={logoRef} flying={false} copy={copy.en.phone} delivered={false} />
      </figure>
    </section>
  );

  return (
    <section ref={rootRef} className={styles.hero} aria-labelledby="personal-title" data-signup-state={state.status} data-flight-state={flight ? "flying" : state.status === "success" ? "settled" : "rest"}>
      <div className={styles.content}>
        <p className={styles.eyebrow}>{c.eyebrow}</p>
        <h1 id="personal-title">{c.title}</h1>
        <p className={styles.intro}>{c.benefit}</p>
      </div>
      <div className={styles.capture} id="early-access">
        <p className={styles.invitation}>{c.body}</p>
        <div className={styles.signup}>
          {state.status === "success" ? (
            <div className={styles.confirmation}>
              <span className={styles.check}><Check size={24} aria-hidden="true" /></span>
              <h2 ref={confirmation} tabIndex={-1}>{c.success}</h2>
              {locale === "es" ? <p>Te enviamos un enlace a {email.trim()} para confirmar tu lugar en la lista de la app personal de Cuadrao. Vence en 48 horas.</p> : c.next && <p>{c.next}</p>}
            </div>
          ) : (
            <form method="post" action="/api/waitlist/signups" onSubmit={submit} aria-busy={state.status === "submitting"}>
              <noscript><p className={styles.local}>{c.noScript}</p></noscript>
              <fieldset className={styles.formFields} disabled={!hydrated}>
                <label htmlFor="personal-email">{c.label}</label>
                <div className={styles.emailShell}>
                  <span className={styles.petPerch}><SignupPet petRef={petRef} pose={state.status === "submitting" ? "excited" : state.status === "error" && state.rejected ? "checking" : "rest"} /></span>
                <input id="personal-email" type="email" name="email" value={email} onChange={(event) => {
                  setEmail(event.currentTarget.value);
                  if (state.status === "error" && state.rejected && event.currentTarget.validity.valid) setState({ status: "idle" });
                }} onInvalid={(event) => {
                  event.preventDefault();
                  setState({ status: "error", message: c.invalid, rejected: true });
                  event.currentTarget.focus();
                }} autoComplete="email" inputMode="email" maxLength={254} required aria-describedby={state.status === "error" ? "signup-error signup-privacy" : "signup-privacy"} aria-invalid={(state.status === "error" && state.rejected) || undefined} readOnly={state.status === "submitting"} placeholder={locale === "es" ? "tu@correo.com" : "you@example.com"} />
                </div>
                {locale === "es" && <div className={styles.optionalFields}>
                  <label htmlFor="personal-expenses">¿Cómo llevas hoy tus gastos?</label>
                  <select id="personal-expenses" name="expenseMethod" value={expenseMethod} onChange={(event) => setExpenseMethod(event.target.value)} disabled={state.status === "submitting"}>
                    <option value=""></option>
                    {EXPENSE_METHODS.map((method) => <option key={method} value={method}>{method}</option>)}
                  </select>
                  <label htmlFor="personal-wish">¿Qué te gustaría que Cuadrao te resolviera?</label>
                  <textarea id="personal-wish" name="wish" maxLength={280} value={wish} onChange={(event) => setWish(event.target.value)} aria-describedby="personal-wish-hint personal-wish-digits" readOnly={state.status === "submitting"} />
                  <p id="personal-wish-hint" className={styles.hint}>No incluyas datos de cuentas o tarjetas.</p>
                  <p id="personal-wish-digits" className={styles.error} role="status">{containsSensitiveDigits(wish) ? "Quita los números de cuenta o tarjeta para enviar." : ""}</p>
                  <Link href="/contacto">¿Es para tu negocio? Escríbenos</Link>
                  <WaitlistCaptcha onToken={setCaptchaToken} attempt={captchaAttempt} />
                </div>}
                <div className={styles.trap} aria-hidden="true">
                  <label htmlFor="personal-website">{locale === "es" ? "Sitio web" : "Website"}</label>
                  <input id="personal-website" name="website" type="text" tabIndex={-1} autoComplete="off" defaultValue="" />
                </div>
                <button ref={buttonRef} type="submit" disabled={!hydrated || (locale === "es" && !captchaToken)} aria-disabled={state.status === "submitting"}>
                  {state.status === "submitting" ? c.saving : c.button}
                  <ArrowRight size={19} aria-hidden="true" />
                </button>
                {locale === "es" && <p className={styles.privacy} id="signup-privacy">Solo te escribiremos sobre la lista y el lanzamiento de la app. <Link href="/privacidad">{c.privacyLink}</Link>.</p>}
                {state.status === "error" && <p id="signup-error" className={styles.error} role="alert">{state.message}</p>}
              </fieldset>
            </form>
          )}
        </div>
      </div>
      <figure className={styles.preview}>
        <WelcomePhone logoRef={logoRef} flying={Boolean(flight)} copy={c.phone} delivered={state.status === "success"} />
      </figure>
      <SignupFlight flight={flight} onFinish={finish} />
    </section>
  );
}
