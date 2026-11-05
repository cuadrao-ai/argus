"use client";
import { useEffect, useId, useRef, useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AVATAR_COLOR_THEMES } from "@/lib/avatar-theme";
import {
  DEFAULT_APPEARANCE,
  loadIdentityImage,
  renderIdentityImage,
  type IdentityAppearance,
  type IdentityImage,
} from "@/lib/identity-appearance";
import {
  primaryButtonClass,
  quietButtonClass,
} from "@/components/business-app/business-ui";
import { FOCUS_RING } from "@/components/business-app/foundation/presentation";
import pointerAffordances from "@/components/sidebar/pointerAffordances.module.css";
import { IdentityMark } from "./IdentityMark";

const PREVIEW_SIZE = 160;
const SELECTED_RING =
  "outline outline-2 outline-offset-2 outline-[var(--cuadrao-green)]";
const FOCUSED_RADIO_RING =
  "has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--cuadrao-green)]";

export default function IdentityEditor({
  saved,
  name,
  business = false,
  onBack,
  onSave,
}: {
  saved: IdentityAppearance;
  name: string;
  business?: boolean;
  onBack?: () => void;
  onSave: (appearance: IdentityAppearance) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const group = useId();
  const [draft, setDraft] = useState<IdentityAppearance>(
    saved.kind === "avatar" ? { ...saved, mark: "initials" } : saved,
  );
  const [image, setImage] = useState<IdentityImage | null>(
    saved.kind === "image" ? saved : null,
  );
  const [busy, setBusy] = useState<"file" | "save" | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0),
    fileRef = useRef<HTMLInputElement>(null),
    uploadRef = useRef<HTMLButtonElement>(null);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  const choose = (next: IdentityAppearance) => {
    setDraft(next);
    setError(null);
  };
  const file = async (value: File) => {
    const request = ++generation.current;
    setBusy("file");
    setError(null);
    try {
      const next = await renderIdentityImage({
        ...(await loadIdentityImage(value)),
        crop: { mode: business ? "fit" : "fill", zoom: 1, x: 0, y: 0 },
      });
      if (request === generation.current) {
        setImage(next);
        setDraft(next);
      }
    } catch (e) {
      if (request === generation.current)
        setError(e instanceof Error ? e.message : "file_decode");
    } finally {
      if (request === generation.current) setBusy(null);
    }
  };
  const save = async () => {
    if (busy) return;
    setBusy("save");
    setError(null);
    try {
      await onSave(draft);
    } catch {
      setError("save_error");
    } finally {
      setBusy(null);
    }
  };
  const selected = draft.kind === "avatar" ? draft.token : draft.kind;
  const imageSelected = draft.kind === "image";
  const restoresImage = image !== null && !imageSelected;
  const uploadFilled = image !== null && busy !== "file";
  const UploadIcon = busy === "file" ? Loader2 : Plus;
  const choices: {
    key: string;
    label: string;
    appearance: IdentityAppearance;
  }[] = [
    {
      key: "default",
      label: t("identity.default_icon"),
      appearance: DEFAULT_APPEARANCE,
    },
    ...AVATAR_COLOR_THEMES.map(({ token }) => ({
      key: token,
      label: t(`settings.profile.avatar_theme.themes.${token}`),
      appearance: { kind: "avatar", token, mark: "initials" } as const,
    })),
  ];
  const tile = `relative flex aspect-square overflow-hidden border border-[var(--segment-thumb-border)] ${business ? "rounded-item" : "rounded-full"}`;
  return (
    <div className="space-y-[21px] pt-[13px] lg:pt-0" data-testid="identity-editor">
      {onBack ? (
        <button type="button" className={quietButtonClass} onClick={onBack}>
          {t("common.back")}
        </button>
      ) : null}
      <div className="flex flex-col items-center gap-2">
        <div
          role="img"
          aria-label={t("identity.preview")}
          data-testid="identity-preview"
          data-drag={dragging ? "accept" : "idle"}
          className={`overflow-hidden ${business ? "rounded-surface" : "rounded-full"} ${dragging ? "outline outline-2 outline-[var(--cuadrao-green)] ring-4 ring-[#2f5a49]/15" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = busy ? "none" : "copy";
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const dropped = event.dataTransfer.files[0];
            if (dropped && !busy) void file(dropped);
          }}
        >
          <span className="pointer-events-none flex">
            <IdentityMark
              appearance={draft}
              name={name}
              business={business}
              size={PREVIEW_SIZE}
            />
          </span>
        </div>
        {image ? (
          <button
            type="button"
            disabled={busy !== null}
            className={`${quietButtonClass} ${draft.kind === "image" ? "" : "invisible"}`}
            onClick={() => {
              setImage(null);
              choose(DEFAULT_APPEARANCE);
              uploadRef.current?.focus();
            }}
          >
            {t("identity.remove")}
          </button>
        ) : null}
      </div>
      <div className="@container">
        <div className="grid grid-cols-4 gap-2 @min-[408px]:grid-cols-8">
          <button
            ref={uploadRef}
            type="button"
            data-testid="identity-upload"
            disabled={busy !== null}
            aria-busy={busy === "file"}
            aria-pressed={image ? imageSelected : undefined}
            aria-label={t(
              restoresImage
                ? business
                  ? "identity.image"
                  : "identity.photo"
                : business
                  ? "identity.choose_image"
                  : "identity.choose_photo",
            )}
            className={`group items-center justify-center transition-colors motion-reduce:transition-none disabled:opacity-40 ${tile} ${uploadFilled ? "" : "border-dashed text-[#56635e] hover:border-[var(--cuadrao-green)] hover:bg-[#2f5a49]/[0.03] dark:text-white/70"} ${imageSelected ? SELECTED_RING : ""} ${FOCUS_RING}`}
            onClick={() =>
              restoresImage ? choose(image) : fileRef.current?.click()
            }
          >
            {uploadFilled ? (
              <>
                <IdentityMark
                  appearance={image}
                  name={name}
                  business={business}
                  size="fill"
                />
                {imageSelected ? (
                  <span className={`absolute inset-0 flex items-center justify-center bg-black/45 text-white transition-opacity motion-reduce:transition-none ${pointerAffordances.replaceCue}`}>
                    <Plus aria-hidden="true" className="h-6 w-6" />
                  </span>
                ) : null}
              </>
            ) : (
              <UploadIcon
                aria-hidden="true"
                className={`h-6 w-6 ${busy === "file" ? "animate-spin motion-reduce:animate-none" : ""}`}
              />
            )}
          </button>
          <div
            role="radiogroup"
            aria-label={t("identity.change_image")}
            className="contents"
          >
            {choices.map(({ key, label, appearance }) => (
              <label
                key={key}
                className={`cursor-pointer transition-opacity hover:opacity-90 motion-reduce:transition-none ${tile} ${FOCUSED_RADIO_RING} ${key === selected ? SELECTED_RING : ""}`}
              >
                <input
                  type="radio"
                  name={group}
                  className="sr-only"
                  aria-label={label}
                  checked={key === selected}
                  disabled={busy !== null}
                  onChange={() => choose(appearance)}
                />
                <IdentityMark
                  appearance={appearance}
                  name={name}
                  business={business}
                  size="fill"
                />
              </label>
            ))}
          </div>
        </div>
        <input
          ref={fileRef}
          hidden
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            event.target.value = "";
            if (picked) void file(picked);
          }}
        />
      </div>
      {error ? (
        <p
          role="alert"
          className="text-[14px] text-[#b52335] dark:text-[#ff929c]"
        >
          {t(`identity.${error}`)}
        </p>
      ) : null}
      <div className="border-t border-black/10 pt-4 dark:border-white/10">
        <button
          type="button"
          disabled={
            busy !== null || JSON.stringify(draft) === JSON.stringify(saved)
          }
          className={`${primaryButtonClass} w-full`}
          onClick={() => void save()}
        >
          {t(
            busy === "save"
              ? "identity.working"
              : business
                ? "identity.save_image"
                : "identity.save_photo",
          )}
        </button>
      </div>
    </div>
  );
}
