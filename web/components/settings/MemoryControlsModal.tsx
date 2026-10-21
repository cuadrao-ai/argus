"use client";

import { Switch } from "@/components/ui/Switch";
import {
  useCallback,
  useEffect,
  useState,
  type RefObject,
} from "react";
import {
  Check,
  Download,
  Info,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  ALL_MEMORY_CATEGORIES,
  deleteMemoryRecord,
  disableMemory,
  editMemoryRecord,
  enableMemory,
  explainMemoryRecord,
  exportMemory,
  getMemorySettings,
  listMemoryRecords,
  resetMemory,
  type MemoryExplanation,
  type MemoryRecord,
  type MemorySettings,
} from "@/lib/memory-api";

type MemoryControlsModalProps = {
  locale: "en-US" | "es-419";
  onClose: () => void;
  onBack?: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
  backLabel?: string;
};

type RecordRowProps = {
  record: MemoryRecord;
  locale: "en-US" | "es-419";
  onEdited: (record: MemoryRecord) => void;
  onDeleted: (recordId: string) => void;
};

function categoryLabel(
  category: string,
  t: ReturnType<typeof useTranslation>["t"],
): string {
  const fallback: Record<string, string> = {
    personalization_preference: "Personalization preference",
    workflow_preference: "Workflow preference",
    explicit_decision_note: "Saved decision",
    past_session_anchor: "Past session anchor",
  };
  return t(
    `settings.data.personalization.categories.${category}`,
    fallback[category] ?? category,
  );
}

function formatDate(value: string, locale: "en-US" | "es-419"): string {
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function MemoryRecordRow({ record, locale, onEdited, onDeleted }: RecordRowProps) {
  const { t } = useTranslation();
  const [explanation, setExplanation] = useState<MemoryExplanation | null>(null);
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(record.label);
  const [editValue, setEditValue] = useState(record.value);
  const [isBusy, setIsBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const toggleExplanation = useCallback(async () => {
    setRowError(null);
    if (explanationOpen) {
      setExplanationOpen(false);
      return;
    }
    try {
      if (!explanation) {
        setExplanation(await explainMemoryRecord(record.id));
      }
      setExplanationOpen(true);
    } catch {
      setRowError(
        t(
          "settings.data.personalization.errors.explain",
          "Could not load the explanation. Try again.",
        ),
      );
    }
  }, [explanation, explanationOpen, record.id, t]);

  const saveEdit = useCallback(async () => {
    if (isBusy) return;
    const changes: { value?: string; label?: string } = {};
    if (editLabel.trim() && editLabel !== record.label) {
      changes.label = editLabel.trim();
    }
    if (editValue.trim() && editValue !== record.value) {
      changes.value = editValue.trim();
    }
    if (Object.keys(changes).length === 0) {
      setIsEditing(false);
      return;
    }
    setIsBusy(true);
    setRowError(null);
    try {
      const result = await editMemoryRecord(record.id, changes);
      if (result.changed && result.record) {
        onEdited(result.record);
      }
      setIsEditing(false);
    } catch (error) {
      const code = (error as { code?: string }).code;
      setRowError(
        code === "memory_sensitivity_restricted"
          ? t(
              "settings.data.personalization.errors.restricted",
              "Argus keeps sensitive details out of memory.",
            )
          : t(
              "settings.data.personalization.errors.edit",
              "Could not save that change. Try again.",
            ),
      );
    } finally {
      setIsBusy(false);
    }
  }, [editLabel, editValue, isBusy, onEdited, record, t]);

  const removeRecord = useCallback(async () => {
    if (isBusy) return;
    setIsBusy(true);
    setRowError(null);
    try {
      const result = await deleteMemoryRecord(record.id);
      if (result.changed) {
        onDeleted(record.id);
      }
    } catch {
      setRowError(
        t(
          "settings.data.personalization.errors.delete",
          "Could not delete that memory. Try again.",
        ),
      );
    } finally {
      setIsBusy(false);
      setConfirmingDelete(false);
    }
  }, [isBusy, onDeleted, record.id, t]);

  return (
    <li className="rounded-xl border border-black/[0.06] px-3.5 py-3 dark:border-white/[0.08]">
      {isEditing ? (
        <div className="space-y-2">
          <input
            value={editLabel}
            onChange={(event) => setEditLabel(event.target.value)}
            maxLength={120}
            aria-label={t(
              "settings.data.personalization.edit_label",
              "Memory label",
            )}
            className="w-full rounded-lg border border-black/10 bg-transparent px-2.5 py-1.5 text-[13px] text-black dark:border-white/15 dark:text-white"
          />
          <textarea
            value={editValue}
            onChange={(event) => setEditValue(event.target.value)}
            rows={3}
            maxLength={4096}
            aria-label={t(
              "settings.data.personalization.edit_value",
              "Memory content",
            )}
            className="w-full resize-none rounded-lg border border-black/10 bg-transparent px-2.5 py-1.5 text-[13px] text-black dark:border-white/15 dark:text-white"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setIsEditing(false);
                setEditLabel(record.label);
                setEditValue(record.value);
                setRowError(null);
              }}
              className="inline-flex min-h-9 items-center rounded-full border border-black/10 px-3 text-[12px] font-medium text-black/60 hover:bg-black/[0.04] dark:border-white/15 dark:text-white/60 dark:hover:bg-white/[0.06]"
            >
              {t("common.cancel", "Cancel")}
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => void saveEdit()}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-[#191c1f] px-3.5 text-[12px] font-medium text-white hover:bg-black disabled:opacity-55 dark:bg-white dark:text-[#191c1f] dark:hover:bg-white/90"
            >
              <Check className="h-3.5 w-3.5" />
              {t("settings.data.personalization.save_edit", "Save")}
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13px] font-medium text-black dark:text-white">
                {record.label}
              </p>
              <p className="mt-0.5 text-[12.5px] leading-snug text-black/60 dark:text-white/60">
                {record.value}
              </p>
              <p className="mt-1.5 text-[11px] text-black/40 dark:text-white/40">
                {categoryLabel(record.category, t)}
                {" · "}
                {t("settings.data.personalization.saved_on", {
                  date: formatDate(record.created_at, locale),
                  defaultValue: "Saved {{date}}",
                })}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => void toggleExplanation()}
                aria-expanded={explanationOpen}
                className="flex min-h-9 min-w-9 items-center justify-center rounded-full text-black/45 hover:bg-black/5 hover:text-black dark:text-white/45 dark:hover:bg-white/[0.08] dark:hover:text-white"
                aria-label={t(
                  "settings.data.personalization.why_stored",
                  "Why is this stored?",
                )}
              >
                <Info className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="flex min-h-9 min-w-9 items-center justify-center rounded-full text-black/45 hover:bg-black/5 hover:text-black dark:text-white/45 dark:hover:bg-white/[0.08] dark:hover:text-white"
                aria-label={t("settings.data.personalization.edit", "Edit memory")}
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() =>
                  confirmingDelete ? void removeRecord() : setConfirmingDelete(true)
                }
                className={`flex min-h-9 items-center justify-center gap-1 rounded-full px-2 text-[#d66d75] hover:bg-[#d66d75]/10 ${
                  confirmingDelete ? "text-[12px] font-medium" : "min-w-9"
                }`}
                aria-label={t(
                  "settings.data.personalization.delete",
                  "Delete memory",
                )}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {confirmingDelete
                  ? t("settings.data.personalization.confirm_delete", "Confirm?")
                  : null}
              </button>
            </div>
          </div>
          {explanationOpen && explanation ? (
            <div className="mt-2 rounded-lg bg-black/[0.035] px-3 py-2 text-[12px] leading-relaxed text-black/55 dark:bg-white/[0.05] dark:text-white/55">
              <p>
                {t("settings.data.personalization.explanation_intro", {
                  date: formatDate(explanation.confirmed_at, locale),
                  defaultValue: "You confirmed this memory on {{date}}.",
                })}
              </p>
              <p className="mt-1">
                {t("settings.data.personalization.explanation_source", {
                  kind: explanation.provenance[0]?.source_kind ?? "",
                  defaultValue: "Source: {{kind}}.",
                })}
              </p>
            </div>
          ) : null}
        </>
      )}
      {rowError ? (
        <p role="alert" className="mt-2 text-[12px] text-[#b94c55] dark:text-[#e7a2a8]">
          {rowError}
        </p>
      ) : null}
    </li>
  );
}

export default function MemoryControlsModal({
  locale,
  onClose,
  onBack,
  backLabel,
  returnFocusRef,
}: MemoryControlsModalProps) {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<MemorySettings | null>(null);
  const [records, setRecords] = useState<MemoryRecord[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [requestVersion, setRequestVersion] = useState(0);
  const [isMutating, setIsMutating] = useState(false);
  const [surfaceError, setSurfaceError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);

  const retry = useCallback(() => {
    setRequestVersion((current) => current + 1);
  }, []);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setHasError(false);
    Promise.all([getMemorySettings(), listMemoryRecords()])
      .then(([settingsResponse, recordsResponse]) => {
        if (!isCurrent) return;
        setSettings(settingsResponse);
        setRecords(recordsResponse.records);
      })
      .catch(() => {
        if (isCurrent) setHasError(true);
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [requestVersion]);

  const handleToggleMemory = useCallback(async () => {
    if (isMutating || !settings) return;
    setIsMutating(true);
    setSurfaceError(null);
    try {
      if (settings.enabled) {
        await disableMemory();
        setSettings({ enabled: false, enabled_categories: [] });
      } else {
        setSettings(await enableMemory(ALL_MEMORY_CATEGORIES));
      }
    } catch {
      setSurfaceError(
        t(
          "settings.data.personalization.errors.toggle",
          "Could not update memory settings. Try again.",
        ),
      );
    } finally {
      setIsMutating(false);
    }
  }, [isMutating, settings, t]);

  const handleReset = useCallback(async () => {
    if (isMutating) return;
    if (!confirmingReset) {
      setConfirmingReset(true);
      return;
    }
    setIsMutating(true);
    setSurfaceError(null);
    try {
      await resetMemory();
      setSettings({ enabled: false, enabled_categories: [] });
      setRecords([]);
    } catch {
      setSurfaceError(
        t(
          "settings.data.personalization.errors.reset",
          "Could not reset memory. Try again.",
        ),
      );
    } finally {
      setIsMutating(false);
      setConfirmingReset(false);
    }
  }, [confirmingReset, isMutating, t]);

  const handleExport = useCallback(async () => {
    if (isMutating) return;
    setIsMutating(true);
    setSurfaceError(null);
    try {
      const document_ = await exportMemory();
      const blob = new Blob([JSON.stringify(document_, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "argus-memory-export.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch {
      setSurfaceError(
        t(
          "settings.data.personalization.errors.export",
          "Could not export your memory data. Try again.",
        ),
      );
    } finally {
      setIsMutating(false);
    }
  }, [isMutating, t]);

  return (
    <AdaptivePanel
      title={t("settings.data.personalization.title", "Memory")}
      closeLabel={t("settings.data.personalization.close", "Close memory")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
      returnFocusRef={returnFocusRef}
    >
        <div className="overflow-y-auto px-5 pb-5" aria-live="polite">
          {isLoading ? (
            <div
              className="flex min-h-56 flex-col items-center justify-center gap-3 text-[13px] text-black/40 dark:text-white/40"
              role="status"
            >
              <Loader2 className="h-5 w-5 animate-spin" />
              {t("settings.data.personalization.loading", "Loading memory...")}
            </div>
          ) : hasError || settings === null || records === null ? (
            <div className="flex min-h-56 flex-col items-center justify-center gap-4 text-center">
              <p className="text-[13px] text-black/50 dark:text-white/50">
                {t(
                  "settings.data.personalization.load_error",
                  "Memory could not be loaded.",
                )}
              </p>
              <button
                type="button"
                onClick={retry}
                className="flex min-h-11 items-center gap-2 rounded-xl bg-black/[0.06] px-3.5 py-2 text-[12px] font-medium text-black/70 hover:bg-black/[0.09] dark:bg-white/[0.08] dark:text-white/70 dark:hover:bg-white/[0.12]"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {t("settings.data.personalization.retry", "Try again")}
              </button>
            </div>
          ) : (
            <div className="pt-1">
              <p className="text-[12.5px] leading-relaxed text-black/55 dark:text-white/55">
                {t(
                  "settings.data.personalization.intro",
                  "Argus only remembers what you confirm. You can review, edit, delete, or turn off everything here.",
                )}
              </p>

              <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-black/[0.06] px-3.5 py-3 dark:border-white/[0.08]">
                <div>
                  <p className="text-[13px] font-medium text-black dark:text-white">
                    {t(
                      "settings.data.personalization.toggle_label",
                      "Remember confirmed memories",
                    )}
                  </p>
                  <p className="mt-0.5 text-[11.5px] text-black/45 dark:text-white/45">
                    {settings.enabled
                      ? t(
                          "settings.data.personalization.toggle_on_note",
                          "On. New memories still need your confirmation.",
                        )
                      : t(
                          "settings.data.personalization.toggle_off_note",
                          "Off. Existing memories stay until you delete them.",
                        )}
                  </p>
                </div>
                <Switch
                  checked={settings.enabled}
                  onChange={() => handleToggleMemory()}
                  label={t(
                    "settings.data.personalization.toggle_label",
                    "Remember confirmed memories",
                  )}
                />
              </div>

              <div className="mt-4">
                <h3 className="text-[13px] font-medium text-black dark:text-white">
                  {t(
                    "settings.data.personalization.records_title",
                    "What Argus remembers",
                  )}
                </h3>
                {records.length === 0 ? (
                  <p className="mt-2 text-[12.5px] text-black/45 dark:text-white/45">
                    {t(
                      "settings.data.personalization.empty",
                      "Nothing yet. When you confirm a memory it will appear here.",
                    )}
                  </p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {records.map((record) => (
                      <MemoryRecordRow
                        key={record.id}
                        record={record}
                        locale={locale}
                        onEdited={(edited) =>
                          setRecords((current) =>
                            (current ?? []).map((item) =>
                              item.id === edited.id ? edited : item,
                            ),
                          )
                        }
                        onDeleted={(recordId) =>
                          setRecords((current) =>
                            (current ?? []).filter((item) => item.id !== recordId),
                          )
                        }
                      />
                    ))}
                  </ul>
                )}
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-black/[0.05] pt-4 dark:border-white/[0.06]">
                <button
                  type="button"
                  disabled={isMutating}
                  onClick={() => void handleExport()}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-black/10 px-3.5 text-[12px] font-medium text-black/70 hover:bg-black/[0.04] disabled:opacity-55 dark:border-white/15 dark:text-white/70 dark:hover:bg-white/[0.06]"
                >
                  <Download className="h-3.5 w-3.5" />
                  {t("settings.data.personalization.export", "Export memory data")}
                </button>
                <button
                  type="button"
                  disabled={isMutating}
                  onClick={() => void handleReset()}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-full px-3.5 text-[12px] font-medium text-[#d66d75] hover:bg-[#d66d75]/10 disabled:opacity-55"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {confirmingReset
                    ? t(
                        "settings.data.personalization.reset_confirm",
                        "Delete everything?",
                      )
                    : t("settings.data.personalization.reset", "Reset memory")}
                </button>
              </div>

              {surfaceError ? (
                <p
                  role="alert"
                  className="mt-3 text-[12px] text-[#b94c55] dark:text-[#e7a2a8]"
                >
                  {surfaceError}
                </p>
              ) : null}
            </div>
          )}
        </div>
    </AdaptivePanel>
  );
}
