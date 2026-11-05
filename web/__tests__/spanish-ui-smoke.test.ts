import { expect, test, describe } from "bun:test";
import fs from "fs";
import path from "path";

describe("Spanish UI Smoke Harness", () => {
  const originalEnv = process.env.NEXT_PUBLIC_ENABLE_SPANISH;
  const webRoot = path.resolve(__dirname, "..");
  const esLocalePath = path.join(webRoot, "public/locales/es-419/common.json");
  const enLocalePath = path.join(webRoot, "public/locales/en/common.json");

  const requiredSmokeKeys = [
    "chat.input_placeholder",
    "chat.message_empty",
    "chat.send_message",
    "chat.disclaimer",
    "chat.backtest_job.queued_title",
    "chat.backtest_job.queued_status",
    "chat.backtest_job.running_title",
    "chat.backtest_job.running_status",
    "chat.backtest_job.succeeded_title",
    "chat.backtest_job.succeeded_status",
    "chat.backtest_job.failed_title",
    "chat.backtest_job.failed_status",
    "chat.backtest_job.expired_title",
    "chat.backtest_job.expired_status",
    "chat.confirmation.status.ready_to_run",
    "chat.confirmation.status.running",
    "chat.confirmation.status.run_complete",
    "chat.confirmation.status.could_not_run",
    "chat.confirmation.rows.assets",
    "chat.confirmation.rows.period",
    "chat.confirmation.actions.run_backtest",
    "chat.confirmation.actions.change_dates",
    "chat.asset_class.equity",
    "chat.asset_class.crypto",
    "chat.asset_class.currency_pair",
    "chat.strategy_type.buy_and_hold",
    "chat.confirmation.contribution_periods.daily",
    "chat.confirmation.contribution_periods.weekly",
    "chat.confirmation.contribution_periods.biweekly",
    "chat.confirmation.contribution_periods.monthly",
    "chat.confirmation.contribution_periods.quarterly",
    "settings.title",
    "settings.profile.title",
    "settings.profile.delete_account",
    "settings.app.language",
    "settings.sidebar.title",
    "settings.sidebar.description",
    "settings.sidebar.expanded",
    "settings.sidebar.collapsed",
    "settings.sidebar.hover",
    "settings.sidebar.close",
    "settings.logout",
    "settings.search_language",
    "settings.no_languages",
    "settings.languages.en",
    "settings.languages.es-419",
    "command_palette.ledger.decision_filters",
    "command_palette.ledger.no_saved_ideas",
    "chat.result_followup.headings.general",
    "chat.result_followup.headings.next_experiment",
    "chat.history.pinned",
    "guest.shell.sign_in",
    "guest.shell.settings",
    "guest.shell.language",
    "guest.shell.feedback",
  ];

  const requiredSpanishStaticValues = {
    "auth.login.email_placeholder": "Correo electrónico",
    "auth.login.password_placeholder": "Contraseña",
    "auth.login.subtitle": "Inicia sesión para continuar",
    "auth.login.loading": "Iniciando sesión...",
    "auth.password.show": "Mostrar contraseña",
    "auth.password.hide": "Ocultar contraseña",
    "chat.strategy_type.buy_and_hold": "Comprar y mantener",
    "chat.history.pinned": "Anclados",
    "settings.sidebar.title": "Preferencia de barra lateral",
    "settings.sidebar.description": "Elige cómo se comporta la barra lateral.",
    "settings.sidebar.expanded": "Expandida",
    "settings.sidebar.collapsed": "Solo iconos",
    "settings.sidebar.hover": "Al pasar el cursor",
    "settings.sidebar.close": "Cerrar modal de preferencias de la barra lateral",
    "guest.shell.language": "Idioma",
  };

  function readLocale(localePath: string) {
    expect(fs.existsSync(localePath)).toBe(true);
    return JSON.parse(fs.readFileSync(localePath, "utf-8"));
  }

  function flattenKeys(obj: Record<string, unknown>, prefix = ""): Record<string, string> {
    return Object.keys(obj).reduce((acc: Record<string, string>, k: string) => {
      const pre = prefix.length ? prefix + "." : "";
      const keyPath = pre + k;
      const value = obj[k];

      if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        const nestedValue = value as Record<string, unknown>;
        if (Object.keys(nestedValue).length === 0) {
          acc[keyPath] = "{}";
        } else {
          Object.assign(acc, flattenKeys(nestedValue, keyPath));
        }
      } else if (Array.isArray(value)) {
        if (value.length === 0) {
          acc[keyPath] = "[]";
        } else {
          value.forEach((item: unknown, index: number) => {
            const itemPath = keyPath + "[" + index + "]";
            if (typeof item === "object" && item !== null && !Array.isArray(item)) {
              const nestedItem = item as Record<string, unknown>;
              if (Object.keys(nestedItem).length === 0) {
                acc[itemPath] = "{}";
              } else {
                Object.assign(acc, flattenKeys(nestedItem, itemPath));
              }
            } else {
              acc[itemPath] = String(item);
            }
          });
        }
      } else {
        acc[keyPath] = String(value);
      }
      return acc;
    }, {});
  }

  function extractPlaceholders(text: string): string[] {
    const matches = text.match(/{{[^}]+}}/g);
    return matches ? matches.sort() : [];
  }

  function valueAtPath(source: unknown, keyPath: string): unknown {
    return keyPath.split(".").reduce<unknown>((current, segment) => {
      if (!current || typeof current !== "object") return undefined;
      return (current as Record<string, unknown>)[segment];
    }, source);
  }

  test("Spanish locale JSON exists and parses", () => {
    const json = readLocale(esLocalePath);
    expect(json).toBeDefined();
  });

  test("non-retryable discovery copy makes no temporal promise in either locale", () => {
    const locales = {
      en: readLocale(enLocalePath),
      "es-419": readLocale(esLocalePath),
    };
    const cases = [
      {
        locale: "en" as const,
        expected:
          "Current source-backed discovery is not available for this request, and I will not guess from memory. Name a symbol or company you already have in mind and I can test it. Everything in this chat is unchanged.",
      },
      {
        locale: "es-419" as const,
        expected:
          "La búsqueda actual respaldada por fuentes no está disponible para esta solicitud, y no voy a adivinar de memoria. Dime un símbolo o una empresa que tengas en mente y puedo probarla. Todo en este chat sigue igual.",
      },
    ];

    for (const { locale, expected } of cases) {
      expect(valueAtPath(locales[locale], "chat.recovery.discovery_unavailable")).toBe(
        expected,
      );
    }
  });

  test("Spanish smoke keys exist for the private-alpha UI surface", () => {
    const en = readLocale(enLocalePath);
    const es = readLocale(esLocalePath);

    for (const key of requiredSmokeKeys) {
      expect(valueAtPath(en, key), `missing English key ${key}`).toBeString();
      expect(valueAtPath(es, key), `missing Spanish key ${key}`).toBeString();
      expect(String(valueAtPath(es, key)).trim(), `blank Spanish key ${key}`).not.toBe("");
    }
  });

  test("required Spanish static UI values do not fall back to English", () => {
    const es = readLocale(esLocalePath);

    for (const [key, expectedValue] of Object.entries(requiredSpanishStaticValues)) {
      expect(valueAtPath(es, key), `unexpected Spanish value for ${key}`).toBe(expectedValue);
    }
  });

  test("Source referencing verified keys", () => {
    // Basic checks to ensure source files still reference keys that exist in Spanish bundle
    const languageSource = fs.readFileSync(path.join(webRoot, "components/settings/LanguageModal.tsx"), "utf-8");
    expect(languageSource).toContain("settings.search_language");

    const chatSource = fs.readFileSync(path.join(webRoot, "components/chat/ChatInput.tsx"), "utf-8");
    expect(chatSource).toContain("chat.message_empty");

    const backtestSource = fs.readFileSync(path.join(webRoot, "lib/backtest-job-card-copy.ts"), "utf-8");
    expect(backtestSource).toContain("chat.backtest_job.queued_title");

    const confirmationSource = fs.readFileSync(
      path.join(webRoot, "components/chat/confirmation-display.ts"),
      "utf-8",
    );
    expect(confirmationSource).toContain("chat.confirmation.status.ready_to_run");
    expect(confirmationSource).toContain("chat.confirmation.rows.assets");
    expect(confirmationSource).toContain("chat.confirmation.actions.run_backtest");

    const sidebarPreferenceSource = fs.readFileSync(
      path.join(webRoot, "components/settings/SidebarPreferenceModal.tsx"),
      "utf-8",
    );
    const sidebarSource = fs.readFileSync(
      path.join(webRoot, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );
    const recentsSource = fs.readFileSync(
      path.join(webRoot, "lib/chat-recents.ts"),
      "utf-8",
    );

    expect(sidebarPreferenceSource).toContain('closeLabel={t("settings.sidebar.close")}');
    for (const key of [
      "settings.sidebar.title",
      "settings.sidebar.description",
      "settings.sidebar.expanded",
      "settings.sidebar.collapsed",
      "settings.sidebar.hover",
    ]) {
      expect(sidebarPreferenceSource).toContain(`t("${key}")`);
      expect(sidebarPreferenceSource).not.toContain(`t("${key}",`);
    }
    expect(recentsSource).toContain('["pinned", true]');
    expect(sidebarSource).toContain("{group.isPinned &&");
    expect(sidebarSource).not.toContain('group.label === t("chat.history.pinned",');
  });

  test("Confirmation cards do not use translated display labels as state", () => {
    const cardSource = fs.readFileSync(
      path.join(webRoot, "components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );
    const historySource = fs.readFileSync(
      path.join(webRoot, "components/chat/artifact-history.ts"),
      "utf-8",
    );
    const jobSource = fs.readFileSync(path.join(webRoot, "lib/chat-backtest-jobs.ts"), "utf-8");

    expect(cardSource).not.toContain("row.label.toLowerCase()");
    expect(cardSource).not.toContain('normalizedLabel === "running"');
    expect(historySource).not.toContain('new Set(["Running", "Request sent"])');
    expect(jobSource).not.toContain('new Set(["Running", "Request sent"])');
  });

  test("English and Spanish locales should have identical keys", () => {
    const en = flattenKeys(readLocale(enLocalePath));
    const es = flattenKeys(readLocale(esLocalePath));

    const enKeys = Object.keys(en);
    const esKeys = Object.keys(es);

    const missingInEs = enKeys.filter((key) => !esKeys.includes(key));
    const missingInEn = esKeys.filter((key) => !enKeys.includes(key));

    expect(missingInEs).toEqual([]);
    expect(missingInEn).toEqual([]);
  });

  test("Matching keys should have identical placeholders", () => {
    const en = flattenKeys(readLocale(enLocalePath));
    const es = flattenKeys(readLocale(esLocalePath));

    for (const key of Object.keys(en)) {
      expect(Object.prototype.hasOwnProperty.call(es, key)).toBe(true);
      const enPlaceholders = extractPlaceholders(en[key]);
      const esPlaceholders = extractPlaceholders(es[key]);
      expect({ key, placeholders: esPlaceholders }).toEqual({ key, placeholders: enPlaceholders });
    }
  });

  test("Spanish feature flag enables es-419", () => {
    const probe = `
      import { ENABLED_LANGUAGE_CODES, ENABLED_LANGUAGES, SPANISH_ENABLED } from "./lib/language-features.ts";
      if (!SPANISH_ENABLED) throw new Error("Spanish flag did not enable Spanish");
      if (!ENABLED_LANGUAGE_CODES.includes("es-419")) throw new Error("Spanish code missing");
      if (!ENABLED_LANGUAGES.some((language) => language.code === "es-419")) throw new Error("Spanish option missing");
    `;

    try {
      process.env.NEXT_PUBLIC_ENABLE_SPANISH = "true";
      const result = Bun.spawnSync({
        cmd: ["bun", "-e", probe],
        cwd: webRoot,
        env: { ...process.env, NEXT_PUBLIC_ENABLE_SPANISH: "true" },
        stderr: "pipe",
        stdout: "pipe",
      });

      expect(result.exitCode, result.stderr.toString()).toBe(0);
    } finally {
      if (originalEnv === undefined) {
        delete process.env.NEXT_PUBLIC_ENABLE_SPANISH;
      } else {
        process.env.NEXT_PUBLIC_ENABLE_SPANISH = originalEnv;
      }
    }
  });

  test("I18n provider keeps the document language in sync", () => {
    const providerSource = fs.readFileSync(path.join(webRoot, "components/I18nProvider.tsx"), "utf-8");

    expect(providerSource).toContain("document.documentElement.lang");
    expect(providerSource).toContain("languageChanged");
    expect(providerSource).toContain("documentLanguage");
  });
});
