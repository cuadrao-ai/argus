"use client";

import { Check, CircleSlash, Plus, Undo2, X, type LucideIcon } from "lucide-react";
import { useBusiness } from "../BusinessWorkspace";
import type { Decision, Movement } from "./transacciones-model";
import type { TransaccionesController } from "./useTransacciones";
import { useTransaccionesWords } from "./transacciones-words";

export type CommandId = "igualar" | "rechazar" | "agregar" | "sin_comprobante" | "desigualar";

export type Command = Readonly<{ id: CommandId; label: string; key: string; icon: LucideIcon; run: () => void }>;

/** Each command's key and icon; the one table the row, the kebab, the tray and the keyboard read. */
const COMMANDS: Record<CommandId, { key: string; icon: LucideIcon }> = {
  igualar: { key: "I", icon: Check },
  rechazar: { key: "N", icon: X },
  agregar: { key: "A", icon: Plus },
  sin_comprobante: { key: "S", icon: CircleSlash },
  desigualar: { key: "D", icon: Undo2 },
};

/** The commands a row offers now, most likely first: what its state allows and the person may do. The one owner of a state's actions. */
export function useRowCommands(controller: TransaccionesController) {
  const { t } = useTransaccionesWords();
  const { actions, chosen } = useBusiness();
  const upload = chosen?.role !== "accountant" ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  return (movement: Movement): Command[] => {
    const make = (id: CommandId, run: () => void): Command => ({ id, label: t(`business.transactions.actions.${id}`), ...COMMANDS[id], run });
    const match = movement.match;
    const decide = (decision: Decision) => () => void controller.decide(decision);
    const reasons = make("sin_comprobante", () => controller.open(movement.id, "reasons"));
    switch (match.state) {
      case "sugerencia": {
        const { id: suggestionId, document } = match.suggestion;
        return [make("igualar", decide({ kind: "igualar", movementId: movement.id, suggestionId, documentId: document.id })), make("rechazar", decide({ kind: "rechazar", movementId: movement.id, suggestionId })), reasons];
      }
      case "falta_comprobante":
        return upload ? [make("agregar", upload.run), reasons] : [reasons];
      case "igualada":
        return match.document ? [make("desigualar", decide({ kind: "desigualar", movementId: movement.id, outcome: { kind: "match", documentId: match.document.id } }))] : [];
      case "no_lleva":
        // A zero line's own reason is the server's rule, not a choice, so there is nothing to take back.
        return match.reason === "monto_cero" ? [] : [make("desigualar", decide({ kind: "desigualar", movementId: movement.id, outcome: { kind: "no_receipt", reason: match.reason } }))];
      case "sin_movimiento":
        return [];
    }
  };
}

export const commandForKey = (commands: readonly Command[], key: string) => commands.find((command) => command.key.toLowerCase() === key.toLowerCase()) ?? null;
