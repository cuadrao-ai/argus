import { describe, expect, test } from "bun:test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

type LocaleTree = Record<string, unknown>;

const dossierCopy = {
  "command_palette.back_to_latest_run": {
    en: "Back to latest run",
    es419: "Volver a la ejecución más reciente",
  },
  "command_palette.back_to_run_details": {
    en: "Back to run details",
    es419: "Volver a los detalles de la ejecución",
  },
  "command_palette.decision_history": {
    en: "Decision history",
    es419: "Historial de decisiones",
  },
  "command_palette.decision_history_count": {
    en: "{{decided}} of {{total}} decided",
    es419: "{{decided}} de {{total}} con decisión",
  },
  "command_palette.no_decision_saved": {
    en: "No decision saved",
    es419: "Sin decisión guardada",
  },
  "command_palette.add_decision_short": {
    en: "Add decision",
    es419: "Agregar decisión",
  },
  "command_palette.change_decision_short": {
    en: "Edit",
    es419: "Editar",
  },
  "command_palette.open_in_conversation": {
    en: "Open in conversation",
    es419: "Abrir en la conversación",
  },
  "command_palette.load_older": {
    en: "Load older",
    es419: "Cargar anteriores",
  },
  "command_palette.decision_saved": {
    en: "Saved",
    es419: "Guardada",
  },
  "command_palette.decision_history_error": {
    en: "Could not load decision history",
    es419: "No se pudo cargar el historial de decisiones",
  },
  "command_palette.decision_history_retry": {
    en: "Try again",
    es419: "Intentar de nuevo",
  },
  "command_palette.decision_history_loading": {
    en: "Loading decision history",
    es419: "Cargando el historial de decisiones",
  },
  "command_palette.decision_history_loading_older": {
    en: "Loading older decisions",
    es419: "Cargando decisiones anteriores",
  },
  "command_palette.decision_note_label": {
    en: "Decision note: ",
    es419: "Nota de decisión: ",
  },
  "command_palette.decision_note_editor_label": {
    en: "Decision note",
    es419: "Nota de decisión",
  },
  "command_palette.retest_current_data": {
    en: "Retest with current data",
    es419: "Volver a probar con datos actuales",
  },
  "command_palette.retest_tooltip": {
    en: "Reuse this setup with the latest data.",
    es419: "Reutiliza esta configuración con los datos más recientes.",
  },
  "command_palette.show_full_note": {
    en: "Show full note",
    es419: "Mostrar nota completa",
  },
  "command_palette.show_less_note": {
    en: "Show less",
    es419: "Mostrar menos",
  },
  "command_palette.decision_note_count": {
    en: "{{count}} / {{max}}",
    es419: "{{count}} / {{max}}",
  },
  "command_palette.asset_rollup.heading": {
    en: "Your Cuadrao history",
    es419: "Tu historial de Cuadrao",
  },
  "command_palette.asset_rollup.scope_registered": {
    en: "Across your conversations",
    es419: "En todas tus conversaciones",
  },
  "command_palette.asset_rollup.scope_guest": {
    en: "In this temporary conversation",
    es419: "En esta conversación temporal",
  },
  "command_palette.keep_typing_detail": {
    en: "Search starts with a 2-character ticker or a 3-character word.",
    es419: "La búsqueda comienza con un ticker de 2 caracteres o una palabra de 3 caracteres.",
  },
  "command_palette.dossier_values.cadences.daily": {
    en: "Daily",
    es419: "Diaria",
  },
  "command_palette.dossier_values.cadences.weekly": {
    en: "Weekly",
    es419: "Semanal",
  },
  "command_palette.dossier_values.cadences.biweekly": {
    en: "Biweekly",
    es419: "Quincenal",
  },
  "command_palette.dossier_values.cadences.monthly": {
    en: "Monthly",
    es419: "Mensual",
  },
  "command_palette.dossier_values.cadences.quarterly": {
    en: "Quarterly",
    es419: "Trimestral",
  },
  "command_palette.dossier_values.strategy_families.indicator_threshold": {
    en: "RSI threshold",
    es419: "Umbral RSI",
  },
  "command_palette.dossier_values.strategy_families.signal_strategy": {
    en: "Moving-average crossover",
    es419: "Cruce de medias móviles",
  },
} as const;

const conversationActivityCopy = {
  "chat.jump_to_latest": {
    en: "Jump to latest",
    es419: "Ir a lo más reciente",
  },
  "chat.activity.working": {
    en: "Working",
    es419: "En curso",
  },
  "chat.activity.queued": {
    en: "Queued",
    es419: "En espera",
  },
  "chat.activity.checking": {
    en: "Checking status",
    es419: "Consultando el estado",
  },
  "chat.activity.needs_attention": {
    en: "Needs attention",
    es419: "Necesita atención",
  },
  "chat.activity.needs_input": {
    en: "Needs your input",
    es419: "Necesita tu respuesta",
  },
  "chat.activity.new_activity": {
    en: "New activity",
    es419: "Actividad nueva",
  },
  "chat.activity.manual_unread": {
    en: "Marked unread",
    es419: "Marcada como no leída",
  },
  "chat.activity.mark_unread": {
    en: "Mark as unread",
    es419: "Marcar como no leída",
  },
  "chat.activity.mark_read": {
    en: "Mark as read",
    es419: "Marcar como leída",
  },
  "chat.activity.jump_working": {
    en: "Jump to latest; Cuadrao is working below",
    es419: "Ir a lo más reciente; Cuadrao sigue trabajando abajo",
  },
  "chat.activity.jump_new": {
    en: "Jump to new activity",
    es419: "Ir a la actividad nueva",
  },
  "chat.activity.jump_needs_input": {
    en: "Jump to the latest question",
    es419: "Ir a la pregunta más reciente",
  },
  "chat.activity.jump_needs_attention": {
    en: "Jump to the latest recovery",
    es419: "Ir a la recuperación más reciente",
  },
  "chat.activity.mark_read_error": {
    en: "Couldn’t mark this conversation as read. Try again.",
    es419: "No se pudo marcar esta conversación como leída. Inténtalo de nuevo.",
  },
  "chat.activity.mark_unread_error": {
    en: "Couldn’t mark this conversation as unread. Try again.",
    es419:
      "No se pudo marcar esta conversación como no leída. Inténtalo de nuevo.",
  },
  "chat.activity.mark_read_success": {
    en: "Marked as read.",
    es419: "Marcada como leída.",
  },
  "chat.activity.mark_unread_success": {
    en: "Marked as unread.",
    es419: "Marcada como no leída.",
  },
  "chat.activity.announce_working": {
    en: "Cuadrao is working on {{title}}.",
    es419: "Cuadrao está trabajando en {{title}}.",
  },
  "chat.activity.announce_needs_attention": {
    en: "{{title}} needs attention.",
    es419: "{{title}} necesita atención.",
  },
  "chat.activity.announce_needs_input": {
    en: "{{title}} needs your input.",
    es419: "{{title}} necesita tu respuesta.",
  },
  "chat.activity.announce_new_activity": {
    en: "{{title}} is ready.",
    es419: "{{title}} ya está lista.",
  },
} as const;

function translationAt(locale: LocaleTree, dottedKey: string): string | undefined {
  let value: unknown = locale;
  for (const segment of dottedKey.split(".")) {
    if (typeof value !== "object" || value === null || !(segment in value)) {
      return undefined;
    }
    value = (value as LocaleTree)[segment];
  }
  return typeof value === "string" ? value : undefined;
}

function interpolationVariables(value: string): string[] {
  return [...value.matchAll(/{{\s*([a-zA-Z0-9_]+)\s*}}/g)]
    .map((match) => match[1])
    .sort();
}

describe("Omnisearch dossier-history locales", () => {
  test("provides the locked English and natural es-419 copy", () => {
    for (const [key, expected] of Object.entries(dossierCopy)) {
      expect(translationAt(en, key), `${key} English copy`).toBe(expected.en);
      expect(translationAt(es419, key), `${key} es-419 copy`).toBe(
        expected.es419,
      );
    }
  });

  test("keeps interpolation variables equivalent across supported locales", () => {
    for (const key of Object.keys(dossierCopy)) {
      const english = translationAt(en, key);
      const spanish = translationAt(es419, key);

      expect(english, `${key} English copy`).toBeDefined();
      expect(spanish, `${key} es-419 copy`).toBeDefined();
      expect(interpolationVariables(spanish ?? ""), key).toEqual(
        interpolationVariables(english ?? ""),
      );
    }
  });
});

describe("conversation activity locales", () => {
  test("provides exact English and product-reviewed es-419 activity copy", () => {
    for (const [key, expected] of Object.entries(conversationActivityCopy)) {
      expect(translationAt(en, key), `${key} English copy`).toBe(expected.en);
      expect(translationAt(es419, key), `${key} es-419 copy`).toBe(
        expected.es419,
      );
    }
  });

  test("keeps activity announcement interpolation equivalent", () => {
    for (const key of Object.keys(conversationActivityCopy)) {
      const english = translationAt(en, key);
      const spanish = translationAt(es419, key);

      expect(interpolationVariables(spanish ?? ""), key).toEqual(
        interpolationVariables(english ?? ""),
      );
    }
  });
});


describe("business dossier refresh copy", () => {
  test("es-419 supplies the Spanish label and English stays the fallback", () => {
    expect(translationAt(es419, "business.dossier.refresh")).toBe("Consultar registro actual");
    expect(translationAt(en, "business.dossier.refresh")).toBe("Check current record");
  });
});

describe("daily question limit copy", () => {
  test.each([
    [en, "You've reached today's question limit. It resets at {{time}}."],
    [es419, "Llegaste al límite de preguntas de hoy. Se reinicia a las {{time}}."],
  ] as const)("uses Iris's exact copy with no vague wait or em dash", (catalog, expected) => {
    expect(catalog.chat.recovery.daily_cap_reached).toBe(expected);
    expect(catalog.chat.recovery.daily_cap_reached).not.toContain("\u2014");
    expect(catalog.chat.recovery.registered_compute_claim_unavailable).not.toContain("\u2014");
    expect(catalog.chat).not.toHaveProperty("rate_limit_error");
  });
});
