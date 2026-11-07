import Image from "next/image";
import type { ReactNode, Ref } from "react";

import { CuadraoLockup } from "@/components/CuadraoLockup";

const LOCKUP_WIDTH = 200;
const LOCKUP_HEIGHT = Math.round((LOCKUP_WIDTH * 56) / 268);

const actionClass =
  "inline-flex min-h-11 items-center justify-center rounded-full bg-[#2f5a49] px-5 font-sans text-base font-medium text-[#F7F5EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f5a49] focus-visible:ring-offset-2 focus-visible:ring-offset-[#F7F5EE]";

const recoveryActionClass =
  "inline-flex min-h-12 w-full max-w-lg items-center justify-center rounded-full bg-[var(--cuadrao-green)] px-5 py-3 font-sans text-base font-semibold text-[#F7F5EE] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--cuadrao-green)] enabled:cursor-pointer disabled:bg-[var(--segment-track)] disabled:text-[var(--segment-text)] tablet:min-h-[clamp(3.5rem,5.25vw,5rem)] tablet:text-[clamp(1.125rem,1.75vw,1.625rem)] dark:not-disabled:text-[#172b26]";

export function BrandedStatusScreen({
  title,
  detail,
  actionLabel,
  actionHref,
  onAction,
  actionDisabled,
  secondaryLabel,
  secondaryHref,
  reference,
  contactEmail,
  testId,
  variant,
  artwork,
  headingRef,
  busyLabel,
}: {
  title: string;
  detail?: string;
  actionLabel: string;
  actionHref?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
  secondaryLabel?: string;
  secondaryHref?: string;
  /** A ReferenceCode: the short form shows, the full id copies. */
  reference?: ReactNode;
  contactEmail?: string;
  testId?: string;
  variant?: "recovery";
  artwork?: string;
  headingRef?: Ref<HTMLHeadingElement>;
  busyLabel?: string;
}) {
  const recovery = variant === "recovery";
  const primaryClass = recovery ? recoveryActionClass : actionClass;
  const primary = onAction || (recovery && !actionHref) ? (
    <button type="button" className={primaryClass} onClick={onAction} disabled={actionDisabled || Boolean(busyLabel)}>
      {busyLabel ?? actionLabel}
    </button>
  ) : (
    <a href={actionHref} className={primaryClass}>
      {actionLabel}
    </a>
  );

  const content = (
    <>
      {recovery && artwork ? (
        <Image
          unoptimized
          loading="eager"
          src={artwork}
          alt=""
          width={512}
          height={512}
          className="mb-5 h-auto w-[clamp(10rem,16vw,14.5rem)] max-w-full tablet:mb-8"
        />
      ) : null}
      <h1
        ref={headingRef}
        tabIndex={headingRef ? -1 : undefined}
        className={recovery
          ? "max-w-[31rem] wrap-anywhere font-display text-[2.125rem] leading-[1.1] font-medium tracking-tight focus:outline-none tablet:text-[clamp(2.25rem,3.5vw,3.25rem)]"
          : "mt-8 max-w-md text-center font-display text-3xl font-medium tracking-tight"}
      >
        {title}
      </h1>
      {detail ? (
        <p className={recovery
          ? "mt-4 max-w-[38rem] wrap-anywhere font-sans text-base leading-relaxed text-[var(--segment-text)] tablet:mt-6 tablet:text-[clamp(1.125rem,1.75vw,1.625rem)]"
          : "mt-3 max-w-sm text-center font-sans text-base leading-relaxed"}>
          {detail}
        </p>
      ) : null}
      {reference ? (
        <p className="mt-3 text-center font-sans">
          {reference}
        </p>
      ) : null}
      {contactEmail ? (
        <a href={`mailto:${contactEmail}`} className="mt-2 font-sans text-base underline underline-offset-4">
          {contactEmail}
        </a>
      ) : null}
      <div className={recovery
        ? "mt-8 flex w-full justify-center tablet:mt-[clamp(2.5rem,3.75vw,3.5rem)]"
        : "mt-8 flex flex-wrap items-center justify-center gap-3"}>
        {primary}
        {secondaryLabel && secondaryHref ? (
          <a href={secondaryHref} className={actionClass}>
            {secondaryLabel}
          </a>
        ) : null}
      </div>
    </>
  );

  if (recovery) {
    return (
      <main
        data-testid={testId}
        className="grid min-h-dvh grid-rows-[auto_1fr] bg-[var(--cuadrao-cream)] px-6 pt-6 pb-[clamp(4rem,9.5vw,9rem)] text-[var(--segment-text-strong)] tablet:px-[clamp(2rem,3.25vw,3rem)] tablet:pt-[clamp(2rem,3.25vw,3rem)]"
      >
        <header>
          <CuadraoLockup width={274} className="max-w-[min(100%,max(9rem,18.45vw))] align-top" />
        </header>
        <section aria-busy={Boolean(busyLabel)} className="flex min-w-0 flex-col items-center justify-center py-8 text-center">
          {content}
        </section>
        <span role="status" className="sr-only">{busyLabel}</span>
      </main>
    );
  }

  return (
    <main
      data-testid={testId}
      className="flex min-h-dvh flex-col items-center justify-center bg-[#F7F5EE] px-6 py-12 text-[#2f5a49]"
    >
      <Image
        unoptimized
        src="/brand/cuadrao-lockup-light.svg"
        alt=""
        width={LOCKUP_WIDTH}
        height={LOCKUP_HEIGHT}
        className="h-auto w-[200px] max-w-full"
      />
      {content}
    </main>
  );
}
