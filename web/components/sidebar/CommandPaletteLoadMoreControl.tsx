"use client";

import { useTranslation } from "react-i18next";
import { inlineFailureTextClass } from "@/lib/failure-treatment";

type CommandPaletteLoadMoreControlProps = {
  /** A workspace's own words for the failure, in place of the default. */
  errorLabel?: string;
  failed: boolean;
  loading: boolean;
  disabled: boolean;
  onLoadMore: () => void;
};

export default function CommandPaletteLoadMoreControl({
  errorLabel,
  failed,
  loading,
  disabled,
  onLoadMore,
}: CommandPaletteLoadMoreControlProps) {
  const { t } = useTranslation();

  return (
    <div className="mx-2 flex flex-col gap-2">
      {failed && (
        <p
          className={`text-[12px] leading-relaxed ${inlineFailureTextClass}`}
          role="alert"
        >
          {errorLabel ?? t(
            "command_palette.load_more_error",
            "Cuadrao couldn’t load more results. Your current results are still available.",
          )}
        </p>
      )}
      <button
        type="button"
        onClick={onLoadMore}
        disabled={disabled}
        className="rounded-[12px] border border-black/10 px-3 py-2 text-[12px] font-medium text-black/60 hover:bg-black/5 disabled:opacity-50 dark:border-white/10 dark:text-white/60 dark:hover:bg-white/5"
      >
        {loading
          ? t("common.loading")
          : failed
            ? t("command_palette.retry_load_more", "Try loading more")
            : t("common.more", "More")}
      </button>
    </div>
  );
}
