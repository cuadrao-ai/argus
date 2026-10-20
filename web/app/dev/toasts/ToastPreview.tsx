"use client";

import { ToastViewport } from "@/components/business-app/foundation/ToastViewport";
import { showToast, type ToastInput } from "@/components/business-app/foundation/toasts";

// Neutral sample text: this page demonstrates the presenter, not product copy.
const SAMPLES: { id: string; label: string; toast: ToastInput }[] = [
  { id: "info", label: "Info, 4 s", toast: { kind: "info", text: "Dirección copiada." } },
  { id: "success", label: "Success with Deshacer, 8 s", toast: { kind: "success", text: "Marcado como personal. No cuenta en los totales del negocio.", action: { label: "Deshacer", run: () => undefined } } },
  { id: "warning", label: "Warning, 7 s", toast: { kind: "warning", text: "El RNC no coincide con el registro. Revísalo antes de exportar." } },
  { id: "error", label: "Error, stays", toast: { kind: "error", text: "No pudimos guardar ese cambio. El estado volvió a como estaba." } },
];

export default function ToastPreview() {
  return (
    <main className="min-h-[100dvh] bg-[#F7F5EE] px-4 py-6 text-[#172b26] dark:bg-[#141517] dark:text-white">
      <div className="mx-auto flex max-w-xl flex-col gap-3">
        <h1 className="font-display text-[28px] font-medium">Toasts</h1>
        {SAMPLES.map((sample) => (
          <button
            key={sample.id}
            type="button"
            data-testid={`toast-${sample.id}`}
            onClick={() => showToast(sample.toast)}
            className="min-h-11 rounded-full border border-[#7d8a84] bg-white px-5 text-left text-[15px] font-medium dark:bg-[#1f2225]"
          >
            {sample.label}
          </button>
        ))}
      </div>
      <ToastViewport />
    </main>
  );
}
