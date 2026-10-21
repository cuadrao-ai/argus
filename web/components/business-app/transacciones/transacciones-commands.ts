"use client";

import { Check, CircleSlash, Plus, Undo2, X, type LucideIcon } from "lucide-react";
import { useBusiness } from "../BusinessWorkspace";
import { rowActions, type Movement } from "./transacciones-model";
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

/** The commands a row offers now, most likely first: what its state allows, the server takes, and the person may do. */
export function useRowCommands(controller: TransaccionesController) {
  const { t } = useTransaccionesWords();
  const { actions, chosen } = useBusiness();
  const upload = chosen?.role !== "accountant" ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  return (movement: Movement): Command[] => {
    const make = (id: CommandId, run: () => void): Command => ({ id, label: t(`business.transactions.actions.${id}`), ...COMMANDS[id], run });
    const decisions = rowActions(movement, controller.source);
    const commands: Command[] = [];
    const match = movement.match;
    if (match.state === "sugerencia") {
      if (decisions.includes("igualar")) commands.push(make("igualar", () => void controller.decide({ kind: "igualar", movementId: movement.id, suggestionId: match.suggestion.id })));
      if (decisions.includes("rechazar")) commands.push(make("rechazar", () => void controller.decide({ kind: "rechazar", movementId: movement.id, suggestionId: match.suggestion.id })));
    }
    if (match.state === "falta_comprobante" && upload) commands.push(make("agregar", upload.run));
    if (decisions.includes("sin_comprobante")) commands.push(make("sin_comprobante", () => controller.open(movement.id, "reasons")));
    if (decisions.includes("desigualar")) commands.push(make("desigualar", () => void controller.decide({ kind: "desigualar", movementId: movement.id })));
    return commands;
  };
}

export const commandForKey = (commands: readonly Command[], key: string) => commands.find((command) => command.key.toLowerCase() === key.toLowerCase()) ?? null;
