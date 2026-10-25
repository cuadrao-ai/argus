"use client";
import { useEffect, useRef, useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AVATAR_THEMES } from "@/lib/avatar-theme";
import {
  DEFAULT_APPEARANCE,
  imageGeometry,
  loadIdentityImage,
  renderIdentityImage,
  type IdentityAppearance,
  type IdentityCrop,
} from "@/lib/identity-appearance";
import {
  primaryButtonClass,
  quietButtonClass,
  secondaryButtonClass,
} from "@/components/business-app/business-ui";
import { IdentityMark } from "./IdentityMark";
type Adjust = {
  kind: "adjust";
  source: string;
  width: number;
  height: number;
  crop: IdentityCrop;
};
type Step = { kind: "choose" } | Adjust;
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
  const [tab, setTab] = useState<"avatar" | "image">(
    saved.kind === "image" ? "image" : "avatar",
  );
  const [draft, setDraft] = useState(saved),
    [step, setStep] = useState<Step>({ kind: "choose" }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const generation = useRef(0),
    fileRef = useRef<HTMLInputElement>(null),
    drag = useRef<{ x: number; y: number; crop: IdentityCrop } | null>(null);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  const file = async (value: File) => {
    const request = ++generation.current;
    setBusy(true);
    setError(null);
    try {
      const image = await loadIdentityImage(value);
      if (request === generation.current)
        setStep({
          kind: "adjust",
          ...image,
          crop: { mode: business ? "fit" : "fill", zoom: 1, x: 0, y: 0 },
        });
    } catch (e) {
      if (request === generation.current)
        setError(e instanceof Error ? e.message : "file_decode");
    } finally {
      if (request === generation.current) setBusy(false);
    }
  };
  const save = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSave(draft);
    } catch {
      setError("save_error");
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (step.kind !== "adjust" || busy) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await renderIdentityImage(step));
      setStep({ kind: "choose" });
    } catch {
      setError("file_decode");
    } finally {
      setBusy(false);
    }
  };
  const change = (next: Partial<IdentityCrop>) =>
    setStep((current) =>
      current.kind === "adjust"
        ? { ...current, crop: { ...current.crop, ...next } }
        : current,
    );
  const frame =
    step.kind === "adjust"
      ? imageGeometry(step.width, step.height, step.crop)
      : null;
  return (
    <div className="space-y-5" data-testid="identity-editor">
      {step.kind === "adjust" && frame ? (
        <>
          <button
            type="button"
            className={quietButtonClass}
            disabled={busy}
            onClick={() => setStep({ kind: "choose" })}
          >
            {t("common.back")}
          </button>
          <div
            className={`relative mx-auto touch-none overflow-hidden bg-black/5 dark:bg-white/10 ${business ? "rounded-mark" : "rounded-full"}`}
            style={{ width: 256, aspectRatio: "1 / 1", maxWidth: "100%" }}
            onPointerDown={(event) => {
              drag.current = {
                x: event.clientX,
                y: event.clientY,
                crop: step.crop,
              };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!drag.current) return;
              change({
                x: Math.max(
                  -1,
                  Math.min(
                    1,
                    drag.current.crop.x +
                      (event.clientX - drag.current.x) /
                        (event.currentTarget.clientWidth / 2),
                  ),
                ),
                y: Math.max(
                  -1,
                  Math.min(
                    1,
                    drag.current.crop.y +
                      (event.clientY - drag.current.y) /
                        (event.currentTarget.clientWidth / 2),
                  ),
                ),
              });
            }}
            onPointerUp={() => {
              drag.current = null;
            }}
            onPointerCancel={() => {
              drag.current = null;
            }}
          >
            <svg
              viewBox="0 0 256 256"
              className="h-full w-full"
              role="img"
              aria-label={t("identity.preview")}
            >
              <image
                href={step.source}
                x={frame.left}
                y={frame.top}
                width={frame.width}
                height={frame.height}
              />
            </svg>
          </div>
          {business ? (
            <div className="flex flex-wrap gap-2">
              {(["fit", "fill"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={step.crop.mode === mode}
                  className={secondaryButtonClass}
                  onClick={() => change({ mode, zoom: 1, x: 0, y: 0 })}
                >
                  {t(`identity.${mode}`)}
                </button>
              ))}
            </div>
          ) : null}
          {(["zoom", "x", "y"] as const).map((key) => (
            <label key={key} className="block text-[15px] font-medium">
              {t(`identity.${key}`)}
              <input
                aria-label={t(`identity.${key}`)}
                className="block min-h-11 w-full accent-[#2f5a49] dark:accent-[#8fcbb0]"
                type="range"
                min={key === "zoom" ? 1 : -1}
                max={key === "zoom" ? 4 : 1}
                step="0.01"
                value={step.crop[key]}
                onChange={(event) =>
                  change({ [key]: Number(event.target.value) })
                }
              />
            </label>
          ))}
          <button
            type="button"
            className={quietButtonClass}
            onClick={() => change({ zoom: 1, x: 0, y: 0 })}
          >
            {t("identity.recenter")}
          </button>
        </>
      ) : (
        <>
          <>
            {onBack ? (
              <button
                type="button"
                className={quietButtonClass}
                onClick={onBack}
              >
                {t("common.back")}
              </button>
            ) : null}
          </>
          <SegmentedControl
            fill
            label={t("identity.change_image")}
            value={tab}
            segments={[
              { key: "avatar", label: t("identity.avatar") },
              {
                key: "image",
                label: t(business ? "identity.image" : "identity.photo"),
              },
            ]}
            onChange={setTab}
          />

          <div className="flex justify-center py-2">
            <IdentityMark
              appearance={draft}
              name={name}
              business={business}
              size={112}
            />
          </div>
          {tab === "image" ? (
            <>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy}
                  className={secondaryButtonClass}
                  onClick={() => fileRef.current?.click()}
                >
                  {t(
                    business
                      ? "identity.choose_image"
                      : "identity.choose_photo",
                  )}
                </button>
                {draft.kind === "image" ? (
                  <button
                    type="button"
                    className={quietButtonClass}
                    onClick={() =>
                      setStep({
                        kind: "adjust",
                        source: draft.source,
                        width: draft.width,
                        height: draft.height,
                        crop: draft.crop,
                      })
                    }
                  >
                    {t("identity.adjust")}
                  </button>
                ) : null}
                {draft.kind === "image" ? (
                  <button
                    type="button"
                    className={quietButtonClass}
                    onClick={() => setDraft(DEFAULT_APPEARANCE)}
                  >
                    {t("identity.remove")}
                  </button>
                ) : null}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                aria-label={t("identity.image")}
                onChange={(event) => {
                  const picked = event.target.files?.[0];
                  event.target.value = "";
                  if (picked) void file(picked);
                }}
              />
              <p className="text-[14px] text-[#56635e] dark:text-white/70">
                {t("identity.file_hint")}
              </p>
            </>
          ) : null}
          {tab === "avatar" ? (
            <>
              <fieldset>
                <legend className="mb-2 text-[15px] font-medium">
                  {t("identity.avatar")}
                </legend>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    aria-label={t("identity.default_icon")}
                    aria-pressed={draft.kind === "default"}
                    className="flex min-h-11 min-w-11 items-center justify-center rounded-item"
                    onClick={() => setDraft(DEFAULT_APPEARANCE)}
                  >
                    <IdentityMark
                      appearance={DEFAULT_APPEARANCE}
                      business={business}
                      name={name}
                    />
                  </button>
                  {AVATAR_THEMES.map((theme) => (
                    <button
                      key={theme.token}
                      type="button"
                      className="flex min-h-11 min-w-11 items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2"
                      aria-label={t(
                        `settings.profile.avatar_theme.themes.${theme.token}`,
                      )}
                      aria-pressed={
                        draft.kind === "avatar" && draft.token === theme.token
                      }
                      onClick={() =>
                        setDraft({
                          kind: "avatar",
                          token: theme.token,
                          mark:
                            draft.kind === "avatar" ? draft.mark : "initials",
                        })
                      }
                    >
                      <span
                        className={
                          draft.kind === "avatar" && draft.token === theme.token
                            ? `relative ${business ? "rounded-mark" : "rounded-full"} ring-2 ring-[#2f5a49] ring-offset-2 dark:ring-[#8fcbb0] dark:ring-offset-[#1f2225]`
                            : ""
                        }
                      >
                        <IdentityMark
                          appearance={{
                            kind: "avatar",
                            token: theme.token,
                            mark: "initials",
                          }}
                          name={name}
                          business={business}
                        />
                        {draft.kind === "avatar" &&
                        draft.token === theme.token ? (
                          <Check
                            aria-hidden="true"
                            className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full bg-[#2f5a49] p-0.5 text-white dark:bg-[#8fcbb0] dark:text-[#172b26]"
                          />
                        ) : null}
                      </span>
                    </button>
                  ))}
                </div>
              </fieldset>
              {draft.kind === "avatar" ? (
                <div className="flex flex-wrap gap-2">
                  {(["initials", "icon"] as const).map((mark) => (
                    <button
                      key={mark}
                      type="button"
                      aria-pressed={draft.mark === mark}
                      className={secondaryButtonClass}
                      onClick={() => setDraft({ ...draft, mark })}
                    >
                      {t(`identity.${mark}`)}
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </>
      )}
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
            busy ||
            (step.kind === "choose" &&
              JSON.stringify(draft) === JSON.stringify(saved))
          }
          className={`${primaryButtonClass} w-full`}
          onClick={() => void (step.kind === "adjust" ? apply() : save())}
        >
          {t(
            busy
              ? "identity.working"
              : step.kind === "adjust"
                ? "identity.use_image"
                : business
                  ? "identity.save_image"
                  : "identity.save_photo",
          )}
        </button>
      </div>
    </div>
  );
}
