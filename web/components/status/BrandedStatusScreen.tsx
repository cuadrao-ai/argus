import Image from "next/image";
import type { ReactNode } from "react";

const LOCKUP_WIDTH = 200;
const LOCKUP_HEIGHT = Math.round((LOCKUP_WIDTH * 56) / 268);

const actionClass =
  "inline-flex min-h-11 items-center justify-center rounded-full bg-[#2f5a49] px-5 font-sans text-base font-medium text-[#F7F5EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f5a49] focus-visible:ring-offset-2 focus-visible:ring-offset-[#F7F5EE]";

export function BrandedStatusScreen({
  title,
  detail,
  actionLabel,
  actionHref,
  onAction,
  secondaryLabel,
  secondaryHref,
  reference,
  contactEmail,
  testId,
}: {
  title: string;
  detail?: string;
  actionLabel: string;
  actionHref?: string;
  onAction?: () => void;
  secondaryLabel?: string;
  secondaryHref?: string;
  /** A ReferenceCode: the short form shows, the full id copies. */
  reference?: ReactNode;
  contactEmail?: string;
  testId?: string;
}) {
  const primary = onAction ? (
    <button type="button" className={actionClass} onClick={onAction}>
      {actionLabel}
    </button>
  ) : (
    <a href={actionHref} className={actionClass}>
      {actionLabel}
    </a>
  );

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
      <h1 className="mt-8 max-w-md text-center font-display text-3xl font-medium tracking-tight">
        {title}
      </h1>
      {detail ? (
        <p className="mt-3 max-w-sm text-center font-sans text-base leading-relaxed">
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
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        {primary}
        {secondaryLabel && secondaryHref ? (
          <a href={secondaryHref} className={actionClass}>
            {secondaryLabel}
          </a>
        ) : null}
      </div>
    </main>
  );
}
