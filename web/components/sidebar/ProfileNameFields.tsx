"use client";

import { Check, Pencil, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { fieldClass, fieldErrorClass, fieldHintClass, fieldLabelClass } from "@/components/ui/form-field";
import type { ApiUser } from "@/lib/argus-api";

const iconButton =
  "flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-40";

/** One name, edited in place: the value and a pencil, then the field with a check and a cross. */
function NameRow({ id, label, hint, value, emptyLabel, editing, draft, setDraft, onStart, onSave, onCancel, saving, error }: {
  id: string;
  label: string;
  hint: string;
  value: string | null | undefined;
  emptyLabel: string;
  editing: boolean;
  draft: string;
  setDraft: (value: string) => void;
  onStart: () => void;
  onSave: () => void | Promise<void>;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}) {
  const { t } = useTranslation();
  return (
    <div data-testid={`profile-name-row-${id}`}>
      <label htmlFor={id} className={fieldLabelClass}>{label}</label>
      {editing ? (
        <div className="mt-2 flex items-center gap-1">
          <input
            id={id}
            autoFocus
            type="text"
            value={draft}
            disabled={saving}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void onSave();
            }}
            aria-describedby={`${id}-hint`}
            className={`min-w-0 flex-1 ${fieldClass}`}
          />
          <button type="button" onClick={() => void onSave()} disabled={saving} aria-label={t("common.save", "Save")} className={`${iconButton} text-[var(--cuadrao-green)] hover:bg-[var(--cuadrao-green)]/10`}>
            <Check className="h-5 w-5" aria-hidden="true" />
          </button>
          <button type="button" onClick={onCancel} disabled={saving} aria-label={t("common.cancel", "Cancel")} className={`${iconButton} text-black/55 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10`}>
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      ) : (
        <button
          id={id}
          type="button"
          onClick={onStart}
          aria-describedby={`${id}-hint`}
          className="group mt-1 flex min-h-11 w-full items-center justify-between gap-3 rounded-item text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]"
        >
          <span className={`min-w-0 truncate text-[16px] ${value ? "" : "text-[#56635e] dark:text-white/60"}`}>{value || emptyLabel}</span>
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/55 group-hover:bg-black/5 dark:text-white/60 dark:group-hover:bg-white/10" aria-hidden="true">
            <Pencil className="h-4 w-4" />
          </span>
        </button>
      )}
      <p id={`${id}-hint`} className={`mt-1 ${fieldHintClass}`}>{hint}</p>
      {error ? <p role="alert" className={`mt-1 ${fieldErrorClass}`}>{error}</p> : null}
    </div>
  );
}

/**
 * Perfil's two names, each edited in place (Lucas, November 3, 2026): the name
 * the team sees on access and history, and the one the Home greeting uses.
 */
export default function ProfileNameFields(props: {
  profile: ApiUser | null;
  editingName: boolean;
  nameValue: string;
  setNameValue: (value: string) => void;
  startEditName: () => void;
  saveName: () => void | Promise<void>;
  stopEditingName: () => void;
  isSavingName: boolean;
  nameError: string | null;
  editingPreferredName: boolean;
  preferredNameValue: string;
  setPreferredNameValue: (value: string) => void;
  startEditPreferredName: () => void;
  savePreferredName: () => void | Promise<void>;
  stopEditingPreferredName: () => void;
  isSavingPreferredName: boolean;
  preferredNameError: string | null;
}) {
  const { t } = useTranslation();
  const { profile } = props;
  return (
    <div className="flex flex-col gap-[21px]" data-testid="profile-names">
      <NameRow
        id="profile-name"
        label={t("settings.profile.name")}
        hint={t("settings.profile.name_team_hint")}
        value={profile?.display_name}
        emptyLabel={t("settings.profile.preferred_name_unset", "Not set")}
        editing={props.editingName}
        draft={props.nameValue}
        setDraft={props.setNameValue}
        onStart={props.startEditName}
        onSave={props.saveName}
        onCancel={props.stopEditingName}
        saving={props.isSavingName}
        error={props.nameError}
      />
      <NameRow
          id="profile-preferred-name"
          label={t("settings.profile.preferred_name")}
          hint={t("settings.profile.preferred_name_hint")}
          value={profile?.preferred_name}
          emptyLabel={t("settings.profile.preferred_name_unset", "Not set")}
          editing={props.editingPreferredName}
          draft={props.preferredNameValue}
          setDraft={props.setPreferredNameValue}
          onStart={props.startEditPreferredName}
          onSave={props.savePreferredName}
          onCancel={props.stopEditingPreferredName}
          saving={props.isSavingPreferredName}
          error={props.preferredNameError}
        />
    </div>
  );
}
