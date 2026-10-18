import Image from "next/image";

const LOCKUP_WIDTH = 200;
const LOCKUP_HEIGHT = Math.round((LOCKUP_WIDTH * 56) / 268);

export function BrandedStatusScreen({
  title,
  detail,
  actionLabel,
  actionHref,
}: {
  title: string;
  detail?: string;
  actionLabel: string;
  actionHref: string;
}) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-[#F7F5EE] px-6 py-12 text-[#2f5a49]">
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
      <a
        href={actionHref}
        className="mt-8 inline-flex min-h-11 items-center justify-center rounded-full bg-[#2f5a49] px-5 font-sans text-base font-medium text-[#F7F5EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f5a49] focus-visible:ring-offset-2 focus-visible:ring-offset-[#F7F5EE]"
      >
        {actionLabel}
      </a>
    </main>
  );
}
