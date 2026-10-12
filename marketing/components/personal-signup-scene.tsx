"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import styles from "./personal-signup-scene.module.css";

const welcome = { src: "/cuadrao-site/personal-welcome-preview.png", width: 1320, height: 2868, logo: { x: 50, y: 41 } } as const;
type Point = Readonly<{ x: number; y: number }>;
type Flight = Readonly<{ pet: Point; envelope: Point; target: Point }>;
const center = (element: HTMLElement): Point => {
  const rect = element.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
};

export function usePersonalSignupScene() {
  const root = useRef<HTMLElement>(null);
  const pet = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const logo = useRef<HTMLSpanElement>(null);
  const [flight, setFlight] = useState<Flight | null>(null);

  useEffect(() => {
    const surface = root.current;
    if (!surface) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    let frame = 0;
    const resetEyes = () => {
      cancelAnimationFrame(frame);
      surface.style.setProperty("--eye-x", "0px");
      surface.style.setProperty("--eye-y", "0px");
    };
    const follow = (event: PointerEvent) => {
      if (reduced.matches || !fine.matches || event.pointerType === "touch" || !pet.current) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!pet.current) return;
        const origin = center(pet.current);
        const dx = event.clientX - origin.x;
        const dy = event.clientY - origin.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        surface.style.setProperty("--eye-x", `${dx / distance * 3}px`);
        surface.style.setProperty("--eye-y", `${dy / distance * 3}px`);
      });
    };
    const settle = () => setFlight(null);
    const preference = () => { resetEyes(); settle(); };
    const keyboard = (event: KeyboardEvent) => { if (event.key === "Tab") resetEyes(); };
    surface.addEventListener("pointermove", follow);
    surface.addEventListener("pointerleave", resetEyes);
    surface.addEventListener("keydown", keyboard);
    window.addEventListener("resize", settle);
    window.addEventListener("scroll", settle, { passive: true });
    reduced.addEventListener("change", preference);
    fine.addEventListener("change", resetEyes);
    return () => {
      cancelAnimationFrame(frame);
      surface.removeEventListener("pointermove", follow);
      surface.removeEventListener("pointerleave", resetEyes);
      surface.removeEventListener("keydown", keyboard);
      window.removeEventListener("resize", settle);
      window.removeEventListener("scroll", settle);
      reduced.removeEventListener("change", preference);
      fine.removeEventListener("change", resetEyes);
    };
  }, []);

  function celebrate() {
    if (!pet.current || !button.current || !logo.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const target = center(logo.current);
    const origin = center(pet.current);
    if ([target, origin].some(({ x, y }) => x < 24 || x > window.innerWidth - 24 || y < 24 || y > window.innerHeight - 24)) return;
    setFlight({ pet: origin, envelope: center(button.current), target });
  }

  return { rootRef: root, petRef: pet, buttonRef: button, logoRef: logo, flight, celebrate, finish: () => setFlight(null) };
}

type Scene = ReturnType<typeof usePersonalSignupScene>;

export function SignupPet({ petRef, pose = "rest" }: { petRef?: Scene["petRef"]; pose?: "rest" | "checking" | "excited" | "delivered" }) {
  return <span ref={petRef} className={styles.pet} data-signup-pet="" data-pose={pose} aria-hidden="true">
    <span className={styles.eyes}><i /><i /></span><span className={styles.smile} />
    <span className={styles.foot} /><span className={styles.foot} />
  </span>;
}

type WelcomePhoneCopy = { alt: string; createAccount: string; signIn: string };

export function WelcomePhone({ logoRef, flying, copy, delivered }: { logoRef: Scene["logoRef"]; flying: boolean; copy: WelcomePhoneCopy; delivered: boolean }) {
  const wrist = useId();
  return <div className={styles.scene} data-welcome-phone="">
    <svg className={styles.palm} viewBox="0 0 480 820" aria-hidden="true">
      <defs><linearGradient id={wrist} x1="0" y1="0" x2="0" y2="1"><stop offset=".73" stopColor="#050505" /><stop offset="1" stopColor="#050505" stopOpacity="0" /></linearGradient></defs>
      <path fill={`url(#${wrist})`} d="M0 820L12 782L13 745Q19 734 34 732C22 694 18 650 17 607L16 543C15 512 25 480 28 445C32 405 23 396 28 372L38 320C43 298 34 276 45 260C55 245 77 243 96 260L116 285L387 264L391 183C393 167 409 151 425 147C441 143 457 151 461 166C470 192 444 220 426 253L425 286L452 314L461 386L449 441L450 517C460 541 457 564 442 592L418 640C408 664 407 690 389 720L324 820Z" />
    </svg>
    <div className={styles.device}>
      <div className={styles.screen}>
        <Image src={welcome.src} width={welcome.width} height={welcome.height} alt={copy.alt} sizes="(max-width: 700px) 240px, 280px" priority />
        <span className={styles.wordmark} aria-hidden="true"><Image src="/cuadrao-site/cuadrao-lockup-light.svg" width={268} height={56} alt="" /></span>
        <span className={styles.heroClearance} aria-hidden="true" />
        <Image className={styles.heroMark} src="/cuadrao-site/cuadrao-mark-light.svg" width={60} height={52} alt="" style={{ left: `${welcome.logo.x}%`, top: `${welcome.logo.y}%` }} />
        <span className={styles.welcomeActions} aria-hidden="true" data-phone-actions="">
          <span>{copy.createAccount}</span>
          <span>{copy.signIn}</span>
        </span>
        <span ref={logoRef} className={styles.logo} style={{ left: `${welcome.logo.x}%`, top: `${welcome.logo.y}%` }} data-phone-logo="" aria-hidden="true">
          {flying && <span className={styles.ripple} />}
          {delivered && !flying && <span className={styles.deliveredPet}><SignupPet pose="delivered" /></span>}
        </span>
      </div>
    </div>
    <svg className={styles.fingers} viewBox="0 0 480 820" aria-hidden="true">
      <g fill="#050505">
        <path d="M368 259C346 259 341 274 346 292C350 309 365 313 390 312L390 340Q389 358 383 375L436 405C460 394 476 374 476 352L477 309C477 281 459 261 433 260Z" />
        <path d="M319 379C296 375 282 381 280 400C278 425 294 446 319 447L386 446L383 482L423 522L468 457C480 439 483 424 471 407C456 385 432 380 405 379Z" />
        <path d="M346 514C328 516 315 525 316 540C317 558 332 568 351 569L385 570L385 594L416 627L443 582C455 564 451 541 441 522C432 505 415 502 399 505Z" />
      </g>
    </svg>
  </div>;
}

export function SignupFlight({ flight, onFinish }: { flight: Flight | null; onFinish: () => void }) {
  if (!flight) return null;
  const { pet, envelope, target } = flight;
  const style = {
    "--pet-x": `${pet.x}px`, "--pet-y": `${pet.y}px`,
    "--from-x": `${envelope.x}px`, "--from-y": `${envelope.y}px`,
    "--to-x": `${target.x}px`, "--to-y": `${target.y}px`,
    "--arc-x": `${envelope.x + (target.x - envelope.x) * .55}px`,
    "--arc-y": `${Math.min(envelope.y, target.y) - 90}px`,
  } as CSSProperties;
  return <div className={styles.flight} style={style} data-signup-flight="" aria-hidden="true">
    <div className={styles.flyingPet} onAnimationEnd={onFinish}><SignupPet pose="excited" /></div>
    <div className={styles.envelope}><svg viewBox="0 0 52 38"><rect x="1" y="1" width="50" height="36" rx="6" fill="#fffdf4" stroke="#294f43" strokeWidth="2" /><path d="m3 4 23 17L49 4M3 34l17-15m12 0 17 15" fill="none" stroke="#294f43" strokeWidth="2" strokeLinejoin="round" /></svg></div>
  </div>;
}
