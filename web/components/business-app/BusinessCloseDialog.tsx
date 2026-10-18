"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { dangerConfirmButtonClass, secondaryButtonClass } from "./business-ui";

export const businessCloseCopyEs = {
  title: "Cerrar este negocio",
  warning: "La ley obliga a tu negocio a guardar sus comprobantes por 10 años. Descárgalos antes de cerrar, porque Cuadrao no los guardará por ti.",
  consequences: "Al cerrar, los miembros pierden acceso de inmediato. Tienes 30 días para reabrirlo. Después, borramos todo y no se puede recuperar.",
  confirmation: "Escribe el nombre del negocio para confirmar.",
  download: "Descargar comprobantes",
  close: "Cerrar negocio",
  cancel: "Cancelar",
};

export type BusinessCloseState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string };

type BusinessCloseCopy = { [Key in keyof typeof businessCloseCopyEs]: string };

/** WIP, unmounted. The caller owns the command journal and existing export. */
export default function BusinessCloseDialog({ businessName, copy, state, exportControl, onConfirm, onCancel }: {
  businessName: string;
  copy: BusinessCloseCopy;
  state: BusinessCloseState;
  exportControl: ReactNode;
  onConfirm: (confirmation: string) => void;
  onCancel: () => void;
}) {
  const inputId = useId();
  const warningId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [confirmation, setConfirmation] = useState("");
  const submitting = state.kind === "submitting";
  const matches = businessName.length > 0 && confirmation === businessName;
  const cancel = () => { if (!submitting) onCancel(); };

  return <AdaptivePanel title={copy.title} closeLabel={copy.cancel} onClose={cancel} width="md" initialFocusRef={inputRef}>
    <form className="space-y-5 p-5" aria-busy={submitting} onSubmit={(event) => { event.preventDefault(); if (matches && !submitting) onConfirm(confirmation); }}>
      <p id={warningId} className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{copy.warning}</p>
      <div>{exportControl}</div>
      <p className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{copy.consequences}</p>
      <div>
        <p className="mb-2 break-words text-[16px] font-semibold">{businessName}</p>
        <label htmlFor={inputId} className="block text-[14px] leading-relaxed">{copy.confirmation}</label>
        <input ref={inputRef} id={inputId} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={submitting} aria-describedby={warningId} autoComplete="off" autoCapitalize="off" spellCheck={false} className="mt-2 min-h-11 w-full rounded-[12px] border border-black/15 bg-transparent px-3 text-[16px] outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:border-white/20 dark:focus-visible:ring-white/30" />
      </div>
      {state.kind === "error" ? <p role="alert" className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{state.message}</p> : null}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={cancel} disabled={submitting} className={secondaryButtonClass}>{copy.cancel}</button>
        <button type="submit" disabled={!matches || submitting} className={dangerConfirmButtonClass}>{copy.close}</button>
      </div>
    </form>
  </AdaptivePanel>;
}
