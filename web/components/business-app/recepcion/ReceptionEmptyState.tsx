import Image from "next/image";
import { quietButtonClass } from "../business-ui";
import inboxArt from "./assets/inbox-empty.png";

export default function ReceptionEmptyState({ title, body, filtered, action }: { title: string; body: string; filtered: boolean; action?: { label: string; run: () => void } }) {
  return <div data-testid="reception-empty" data-empty-kind={filtered ? "filtered" : "first_run"} className="flex flex-col items-center py-12 text-center">
    <Image src={inboxArt} alt="" width={144} height={144} sizes="144px" className="object-contain" />
    <h3 className="mt-4 font-display text-[17px] font-medium text-[#172b26] dark:text-white">{title}</h3>
    <p className="mt-1 max-w-sm text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{body}</p>
    {action ? <button type="button" className={`mt-5 ${quietButtonClass}`} onClick={action.run}>{action.label}</button> : null}
  </div>;
}
