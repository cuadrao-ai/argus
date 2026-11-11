import type { ReceiptCopy } from "@/lib/receipt-copy";
import { RECEIPT_ACTION_BAR_CLEARANCE } from "@/lib/receipt-layout";
import ProvenanceMark from "./ProvenanceMark";
import ReceiptActionBar from "./ReceiptActionBar";

type ReceiptNoticeProps = {
  kind: "revoked" | "unavailable";
  copy: ReceiptCopy;
};

/**
 * The tombstone, and its temporary sibling.
 *
 * A revoked receipt says plainly that it is gone rather than answering 404: the
 * person opening it already holds the link, so a not-found page only makes the
 * sender look careless. A backend that cannot answer right now is a separate
 * state, because telling someone their link is dead when it is not is a lie.
 *
 * Both still offer Try Argus. Someone who followed a link has already shown
 * intent.
 *
 * The notice owns its existing dark surface, so its white copy stays readable
 * when the surrounding conversation shell follows the receiver's light theme.
 */
export default function ReceiptNotice({ kind, copy }: ReceiptNoticeProps) {
  const notice = kind === "revoked" ? copy.tombstone : copy.unavailable;

  return (
    <div className="min-h-dvh w-full bg-[#191c1f]">
      <main
        className={`mx-auto flex w-full max-w-[560px] flex-col gap-5 px-4 pt-7 sm:px-6 sm:pt-10 ${RECEIPT_ACTION_BAR_CLEARANCE}`}
      >
      {/* No payload means no known kind. Do not invent funnel attribution. */}
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11.5px] font-medium uppercase tracking-[0.07em] text-white/40">
          {copy.eyebrow}
        </span>
        <ProvenanceMark label={copy.provenance} />
      </div>
      <section className="rounded-2xl border border-white/[0.10] px-4 py-5">
        <h1 className="font-display text-[19px] font-semibold leading-tight text-white">
          {notice.title}
        </h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-white/60">
          {notice.detail}
        </p>
        {kind === "revoked" && (
          <p className="mt-2 text-[13.5px] leading-relaxed text-white/60">
            {copy.tombstone.cta_detail}
          </p>
        )}
      </section>
      </main>
      {/* A tombstone gets the bar too. Someone who followed a link has already
          shown intent, and the caveat is as true of a dead link as a live one. */}
      <ReceiptActionBar
        framing={copy.framing.headline}
        action={copy.cta.action}
      />
    </div>
  );
}
