"use client";

import ReceiptEditRow from "@/components/business-app/ReceiptEditRow";
import { useTranslation } from "react-i18next";
import { fieldClass, fieldErrorClass, fieldHintClass, fieldLabelClass } from "@/components/ui/form-field";
import type { ApiUser } from "@/lib/argus-api";

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
  return (
    <div data-testid={`profile-name-row-${id}`} role="group" aria-labelledby={`${id}-label`} aria-describedby={`${id}-hint`}>
      {editing
        ? <label id={`${id}-label`} htmlFor={id} className={fieldLabelClass}>{label}</label>
        : <span id={`${id}-label`} className={fieldLabelClass}>{label}</span>}
      <div className="mt-2 py-[11px] max-tablet:py-[7px]">
        <ReceiptEditRow
          label={label}
          value={<span className={`block truncate text-[16px] ${value ? "" : "text-[#56635e] dark:text-white/60"}`}>{value || emptyLabel}</span>}
          open={editing}
          saving={saving}
          locked={saving}
          onOpen={onStart}
          onSave={() => void onSave()}
          onCancel={onCancel}
        >
          <input
            id={id}
            autoFocus
            type="text"
            value={draft}
            disabled={saving}
            onChange={(event) => setDraft(event.target.value)}
            aria-describedby={`${id}-hint`}
            className={`${fieldClass} mt-0! h-11! min-w-0`}
          />
        </ReceiptEditRow>
      </div>
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
