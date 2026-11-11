"use client";

import Link from "next/link";

/**
 * The only action on the page, kept in reach, with the caveat attached to it.
 *
 * A viewer arrives from someone else's message and the action used to sit about
 * 1.4 screens down, so most readers never reached it. Fixed to the bottom it is in
 * the thumb zone from the first paint.
 *
 * The framing travels with the button and is not optional. A call to action that is
 * permanently on screen is mildly promotional on a page a stranger did not ask for,
 * and pairing it with what the page actually is, a what if on prices that already
 * happened, is what makes that acceptable. It also inverts the old arrangement,
 * where the caveat was the thing scrolled past and the button was the thing found.
 *
 * Position is CSS only. There is no scroll listener and no reveal, so the bar cannot
 * behave differently before hydration than after it.
 */

type ReceiptActionBarProps = {
  /** The short framing line. Never omitted. */
  framing: string;
  action: string;
};

export default function ReceiptActionBar({
  framing,
  action,
}: ReceiptActionBarProps) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-[#191c1f]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-[620px] items-center gap-4 px-5 py-3 sm:px-8">
        <p className="min-w-0 flex-1 text-[11.5px] leading-[1.35] text-[#c2a44d]">
          {framing}
        </p>
        <Link
          href="/"
          className="font-display flex min-h-[46px] shrink-0 items-center justify-center rounded-full bg-white px-5 text-[14px] font-medium text-[#191c1f] transition-colors hover:bg-white/90"
        >
          {action}
        </Link>
      </div>
    </div>
  );
}
