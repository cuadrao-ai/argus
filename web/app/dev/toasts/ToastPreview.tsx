"use client";

import { ToastViewport } from "@/components/business-app/foundation/ToastViewport";
import { secondaryButtonClass } from "@/components/business-app/business-ui";
import { showToast, type ToastInput } from "@/components/business-app/foundation/toasts";

// Neutral sample text: this page demonstrates the presenter, not product copy.
const SAMPLES: { id: string; label: string; toast: ToastInput }[] = [
  { id: "info", label: "Info, 4 s", toast: { kind: "info", text: "Dirección copiada." } },
  { id: "success", label: "Success with Deshacer, 8 s", toast: { kind: "success", text: "Marcado como personal. No cuenta en los totales del negocio.", action: { label: "Deshacer", run: () => undefined } } },
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
            className={`${secondaryButtonClass} w-full justify-start`}
          >
            {sample.label}
          </button>
        ))}
      </div>
      <ToastViewport />
    </main>
  );
}
