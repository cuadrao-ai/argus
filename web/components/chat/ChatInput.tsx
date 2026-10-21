import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { TFunction } from "i18next";
import { ArrowUp, AtSign, MessageSquareWarning } from "lucide-react";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { useTranslation } from "react-i18next";
import { searchDiscovery, type DiscoveryItem } from "@/lib/argus-api";
import {
  discoveryPanelDisplay,
  type DiscoverySearchStatus,
} from "@/lib/chat-discovery-panel";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  composerTokenAtCaret,
  composerMentions,
  deleteTokenBeforeOffset,
  findMentionAtOffset,
  isComposerEmpty,
  rangeForButtonDiscoveryQuery,
  rawComposerText,
  rangeForDiscoveryItem,
  replaceRangeWithToken,
  segmentLength,
  serializeComposerSegments,
  type ComposerSegment,
} from "./composer-model";
import { entityTokenClassName } from "./entity-token";
import { noteLandingStarterComposerMatch } from "@/lib/landing-intent";
import type { ChatMention } from "./types";

type ChatInputProps = {
  onSend: (
    text: string,
    mentions?: ChatMention[],
  ) => void | boolean | Promise<void | boolean>;
  disabled?: boolean;
  placeholder?: string;
  onToast?: (message: string) => void;
  draftText?: string | null;
  /**
   * Replaces the asset/indicator mention control. A workspace that passes one
   * has no mention picker at all, including the typed `@` trigger.
   */
  leadingControl?: ReactNode;
  /** Unsent text, so a workspace can keep a draft across navigation. */
  onDraftChange?: (text: string) => void;
  /** Called once a send is accepted. */
  onSent?: () => void;
};

export type DiscoverySection = {
  label: string;
  items: DiscoveryItem[];
};

export const DISCOVERY_SEARCH_LIMIT = 20;

const COMPOSER_TEXT_TRANSFER_TYPES = new Set(["text/plain", "text/uri-list"]);
const COMPOSER_RICH_TEXT_COMPANION_TYPES = new Set(["text/html"]);

type ComposerDataTransferLike = {
  readonly types?: ArrayLike<string>;
  readonly files?: { readonly length: number };
  getData: (format: string) => string;
};

export function plainTextComposerTransferPayload(
  dataTransfer: ComposerDataTransferLike,
) {
  const types = Array.from(dataTransfer.types ?? [], (type) =>
    type.toLowerCase().trim(),
  ).filter(Boolean);
  const text =
    dataTransfer.getData("text/plain") ||
    dataTransfer.getData("text/uri-list") ||
    "";
  const hasFiles = Boolean(dataTransfer.files?.length);
  const hasUnsupportedType = types.some(
    (type) =>
      !COMPOSER_TEXT_TRANSFER_TYPES.has(type) &&
      !COMPOSER_RICH_TEXT_COMPANION_TYPES.has(type),
  );
  const hasRichTextWithoutPlainText =
    !text && types.some((type) => COMPOSER_RICH_TEXT_COMPANION_TYPES.has(type));

  return {
    text,
    rejectedNonText: hasFiles || hasUnsupportedType || hasRichTextWithoutPlainText,
  };
}

export default function ChatInput({
  onSend,
  disabled = false,
  placeholder,
  onToast,
  draftText,
  leadingControl,
  onDraftChange,
  onSent,
}: ChatInputProps) {
  const { t } = useTranslation();
  const [segments, setSegments] = useState<ComposerSegment[]>([{ type: "text", text: "" }]);
  const [composerHasContent, setComposerHasContent] = useState(false);
  const [composerRawText, setComposerRawText] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [discoveryQuery, setDiscoveryQuery] = useState("");
  const [discoveryItems, setDiscoveryItems] = useState<DiscoveryItem[]>([]);
  const [discoveryItemsQuery, setDiscoveryItemsQuery] = useState<string | null>(null);
  const [discoveryStatus, setDiscoveryStatus] =
    useState<DiscoverySearchStatus>("idle");
  const [isDiscoveryOpen, setIsDiscoveryOpen] = useState(false);
  const [activeDiscoveryItemId, setActiveDiscoveryItemId] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);
  const editorRef = useRef<HTMLDivElement>(null);
  const pendingCaretOffsetRef = useRef<number | null>(null);
  const appliedDraftRef = useRef(false);
  const activeMentionOffsetRef = useRef<number | null>(null);
  const buttonDiscoveryAnchorOffsetRef = useRef<number | null>(null);
  const buttonDiscoveryQueryEndOffsetRef = useRef<number | null>(null);
  const composerIsEmpty = !composerHasContent;
  const mentionsEnabled = leadingControl === undefined;
  const onDraftChangeRef = useRef(onDraftChange);
  useLayoutEffect(() => {
    onDraftChangeRef.current = onDraftChange;
  }, [onDraftChange]);

  const inputPlaceholder = placeholder ?? t("chat.input_placeholder");
  const discoverySections = useMemo(
    () => discoverySectionsForDisplay(discoveryItems, discoveryQuery),
    [discoveryItems, discoveryQuery],
  );
  const visibleDiscoveryItems = useMemo(
    () => discoverySections.flatMap((section) => section.items),
    [discoverySections],
  );
  const discoveryItemsAreFresh = discoveryResultsAreFresh(
    discoveryItemsQuery,
    discoveryQuery,
  );
  const selectableDiscoveryItems = useMemo(
    () => selectableDiscoveryItemsForQuery(visibleDiscoveryItems, discoveryItemsAreFresh),
    [discoveryItemsAreFresh, visibleDiscoveryItems],
  );
  const discoveryPanel = discoveryPanelDisplay({
    itemCount: visibleDiscoveryItems.length,
    query: discoveryQuery,
    status: discoveryStatus,
  });
  const activeDiscoveryItem =
    selectableDiscoveryItems.find((item) => item.id === activeDiscoveryItemId) ?? null;
  const activeDiscoveryOptionId = activeDiscoveryItem
    ? discoveryOptionDomId(activeDiscoveryItem.id)
    : undefined;
  const sendButtonDisabled = composerIsEmpty || disabled;
  const sendDisabledReason = composerIsEmpty
    ? t("chat.message_empty", "Message is empty")
    : undefined;
  const sendButtonLabel = t("chat.send_message", "Send message");
  const textOnlyInputMessage = t(
    "chat.text_only_input",
    "Argus can only accept text here right now.",
  );
  const isMentionButtonHidden = shouldHideMentionButton(isDiscoveryOpen, composerRawText);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (appliedDraftRef.current) return;
    const text = draftText?.trim();
    if (!text) return;
    if (composerHasContent || composerRawText.trim()) {
      appliedDraftRef.current = true;
      return;
    }
    appliedDraftRef.current = true;
    pendingCaretOffsetRef.current = text.length;
    setSegments([{ type: "text", text }]);
  }, [composerHasContent, composerRawText, draftText]);

  useEffect(() => {
    if (!mentionsEnabled || !draftText?.trim()) return;
    noteLandingStarterComposerMatch(
      Boolean(appliedDraftRef.current) && composerRawText === draftText,
    );
  }, [composerRawText, draftText, mentionsEnabled]);

  useEffect(() => {
    if (!isDiscoveryOpen) return;
    const query = discoveryQuery.trim();
    if (!query) {
      setDiscoveryItems([]);
      setDiscoveryItemsQuery(null);
      setDiscoveryStatus("idle");
      return;
    }

    let cancelled = false;
    setDiscoveryStatus("loading");
    const timer = setTimeout(() => {
      Promise.allSettled([
        searchDiscovery("assets", query, DISCOVERY_SEARCH_LIMIT),
        searchDiscovery("indicators", query, DISCOVERY_SEARCH_LIMIT),
      ]).then(([assetsResult, indicatorsResult]) => {
        if (cancelled) return;
        const assets =
          assetsResult.status === "fulfilled" ? assetsResult.value?.items ?? [] : [];
        const indicators =
          indicatorsResult.status === "fulfilled"
            ? indicatorsResult.value?.items ?? []
            : [];
        const merged = mergeDiscoveryItems(
          assets,
          indicators,
          query,
          DISCOVERY_SEARCH_LIMIT,
        );
        const didSearchFail =
          assetsResult.status === "rejected" ||
          indicatorsResult.status === "rejected";

        setDiscoveryItems(merged);
        setDiscoveryItemsQuery(query);
        setDiscoveryStatus(
          merged.length > 0 ? "ready" : didSearchFail ? "error" : "empty",
        );
      });
    }, 180);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [discoveryQuery, isDiscoveryOpen]);

  useEffect(() => {
    if (!isDiscoveryOpen || !discoveryItemsAreFresh) {
      setActiveDiscoveryItemId(null);
      return;
    }

    setActiveDiscoveryItemId((current) => {
      if (current && selectableDiscoveryItems.some((item) => item.id === current)) {
        return current;
      }
      return selectableDiscoveryItems[0]?.id ?? null;
    });
  }, [discoveryItemsAreFresh, isDiscoveryOpen, selectableDiscoveryItems]);

  useEffect(() => {
    if (!isDiscoveryOpen || !activeDiscoveryItemId) return;
    document
      .getElementById(discoveryOptionDomId(activeDiscoveryItemId))
      ?.scrollIntoView({ block: "nearest" });
  }, [activeDiscoveryItemId, isDiscoveryOpen]);

  useLayoutEffect(() => {
    writeSegmentsToEditor(editorRef.current, segments);
    setComposerHasContent(!isComposerEmpty(segments));
    setComposerRawText(rawComposerText(segments));
    onDraftChangeRef.current?.(rawComposerText(segments));
    if (pendingCaretOffsetRef.current !== null) {
      const offset = pendingCaretOffsetRef.current;
      pendingCaretOffsetRef.current = null;
      setCaretTextOffset(editorRef.current, offset);
    }
    syncComposerTokenFocus(editorRef.current, segments);
  }, [segments]);

  const readCurrentSegments = () => {
    const current = readSegmentsFromEditor(editorRef.current);
    return current.length > 0 ? current : segments;
  };

  const scheduleComposerTokenFocus = () => {
    window.requestAnimationFrame(() => {
      syncComposerTokenFocus(editorRef.current, readCurrentSegments());
    });
  };

  const updateDiscoveryState = (current: ComposerSegment[], cursor: number | null) => {
    if (!mentionsEnabled) return;
    const rawText = rawComposerText(current);
    const currentCursor = cursor ?? rawText.length;
    const mention = findMentionAtOffset(current, currentCursor);

    if (mention) {
      buttonDiscoveryAnchorOffsetRef.current = null;
      buttonDiscoveryQueryEndOffsetRef.current = null;
      activeMentionOffsetRef.current = currentCursor;
      setIsDiscoveryOpen(true);
      setDiscoveryQuery(mention.query);
      if (!mention.query.trim()) {
        setDiscoveryItems([]);
        setDiscoveryItemsQuery(null);
        setDiscoveryStatus("idle");
      }
      return;
    }

    if (buttonDiscoveryAnchorOffsetRef.current !== null) {
      const anchor = buttonDiscoveryAnchorOffsetRef.current;
      const range = rangeForButtonDiscoveryQuery(rawText, anchor, currentCursor);
      if (!range) {
        closeDiscovery();
        return;
      }
      buttonDiscoveryQueryEndOffsetRef.current = range.end;
      setIsDiscoveryOpen(true);
      setDiscoveryQuery(range.query);
      if (!range.query.trim()) {
        setDiscoveryItems([]);
        setDiscoveryItemsQuery(null);
        setDiscoveryStatus("idle");
      }
      return;
    }

    if (isDiscoveryOpen && !rawComposerText(current).includes("@")) {
      activeMentionOffsetRef.current = null;
      setIsDiscoveryOpen(false);
      setDiscoveryItems([]);
      setDiscoveryItemsQuery(null);
      setDiscoveryStatus("idle");
      setActiveDiscoveryItemId(null);
    }
  };

  const closeDiscovery = () => {
    activeMentionOffsetRef.current = null;
    buttonDiscoveryAnchorOffsetRef.current = null;
    buttonDiscoveryQueryEndOffsetRef.current = null;
    setIsDiscoveryOpen(false);
    setDiscoveryItems([]);
    setDiscoveryItemsQuery(null);
    setDiscoveryStatus("idle");
    setActiveDiscoveryItemId(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    const current = readCurrentSegments();
    const message = serializeComposerSegments(current);
    if (message) {
      const accepted = await onSend(message, composerMentions(current, message));
      if (accepted === false) return;
      onSent?.();
      setSegments([{ type: "text", text: "" }]);
      setComposerHasContent(false);
      setComposerRawText("");
      closeDiscovery();
    }
  };

  const handleContainerClick = () => {
    editorRef.current?.focus();
  };

  const openDiscovery = () => {
    editorRef.current?.focus();
    const current = readCurrentSegments();
    const cursor = getCaretTextOffset(editorRef.current) ?? rawComposerText(current).length;
    const mention = findMentionAtOffset(current, cursor);

    if (!mention && buttonDiscoveryAnchorOffsetRef.current !== null && isDiscoveryOpen) {
      closeDiscovery();
      return;
    }

    if (!mention) {
      activeMentionOffsetRef.current = null;
      buttonDiscoveryAnchorOffsetRef.current = cursor;
      buttonDiscoveryQueryEndOffsetRef.current = cursor;
      setDiscoveryItems([]);
      setDiscoveryItemsQuery(null);
      setDiscoveryStatus("idle");
    } else {
      buttonDiscoveryAnchorOffsetRef.current = null;
      buttonDiscoveryQueryEndOffsetRef.current = null;
      activeMentionOffsetRef.current = cursor;
      if (!mention.query.trim()) {
        setDiscoveryItems([]);
        setDiscoveryItemsQuery(null);
        setDiscoveryStatus("idle");
      }
    }

    setIsDiscoveryOpen(true);
    setDiscoveryQuery(mention?.query ?? "");
  };

  const insertDiscoveryItem = (item: DiscoveryItem) => {
    const current = readCurrentSegments();
    const rawText = rawComposerText(current);
    const cursor =
      activeMentionOffsetRef.current ??
      getCaretTextOffset(editorRef.current) ??
      rawText.length;
    const buttonAnchor = buttonDiscoveryAnchorOffsetRef.current;
    const mention =
      buttonAnchor !== null
        ? rangeForButtonDiscoveryQuery(
            rawText,
            buttonAnchor,
            buttonDiscoveryQueryEndOffsetRef.current ?? cursor,
          ) ?? { start: buttonAnchor, end: buttonAnchor, query: "" }
        : rangeForDiscoveryItem(current, cursor, item) ?? { start: cursor, end: cursor, query: "" };
    const next = replaceRangeWithToken(current, mention, item);
    const tokenEnd = mention.start + item.insert_text.length;
    pendingCaretOffsetRef.current =
      rawText.slice(mention.end).trim().length > 0
        ? rawComposerText(next).length
        : rawComposerText(next)[tokenEnd] === " "
          ? tokenEnd + 1
          : tokenEnd;
    setSegments(next);
    setComposerRawText(rawComposerText(next));
    activeMentionOffsetRef.current = null;
    buttonDiscoveryAnchorOffsetRef.current = null;
    buttonDiscoveryQueryEndOffsetRef.current = null;
    setIsDiscoveryOpen(false);
    setDiscoveryItems([]);
    setDiscoveryItemsQuery(null);
    setDiscoveryStatus("idle");
    setActiveDiscoveryItemId(null);
  };

  const handleEditorInput = () => {
    const current = readCurrentSegments();
    const cursor = getCaretTextOffset(editorRef.current);
    setComposerHasContent(!isComposerEmpty(current));
    setComposerRawText(rawComposerText(current));
    onDraftChangeRef.current?.(rawComposerText(current));
    updateDiscoveryState(current, cursor);
    scheduleComposerTokenFocus();
  };

  const handleComposerDataTransfer = (dataTransfer: ComposerDataTransferLike) => {
    const payload = plainTextComposerTransferPayload(dataTransfer);
    if (payload.rejectedNonText) {
      onToast?.(textOnlyInputMessage);
    }
    if (!payload.text) return;

    editorRef.current?.focus();
    document.execCommand("insertText", false, payload.text);
    handleEditorInput();
  };

  return (
    <form
      onSubmit={handleSubmit}
      onClick={handleContainerClick}
      className="group relative flex min-h-[64px] w-full cursor-text items-center rounded-[32px] border border-black/5 bg-white transition-all focus-within:ring-2 focus-within:ring-black/20 dark:border-white/5 dark:bg-[#1f2227] dark:focus-within:ring-white/20"
    >
      {isDiscoveryOpen && (
        <div
          id="chat-discovery-listbox"
          role="listbox"
          aria-label={t("chat.discovery.prompt", "Mention an asset or indicator")}
          aria-busy={discoveryPanel.busy}
          className="absolute bottom-full left-0 z-30 mb-2 w-full overflow-hidden rounded-[20px] border border-black/10 bg-white dark:border-white/10 dark:bg-[#1f2227]"
        >
          <div
            role={discoveryPanel.failed ? "alert" : undefined}
            className={`flex items-center gap-1.5 border-b border-black/5 px-4 py-2 text-[12px] font-medium dark:border-white/5 ${
              discoveryPanel.failed
                ? inlineFailureTextClass
                : "text-black/45 dark:text-white/45"
            }`}
          >
            {discoveryPanel.failed ? (
              <MessageSquareWarning className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            ) : null}
            {t(discoveryPanel.headerKey, discoveryPanel.headerFallback)}
          </div>
          {discoverySections.length > 0 ? (
            <div className="max-h-64 overflow-y-auto py-1">
              {discoverySections.map((section) => (
                <div key={section.label}>
                  <div className="px-4 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-black/35 dark:text-white/35">
                    {t(discoverySectionLabelKey(section.label), section.label)}
                  </div>
                  {section.items.map((item) => {
                    const itemSelectable = discoveryItemsAreFresh;
                    const isActive = itemSelectable && item.id === activeDiscoveryItemId;
                    return (
                      <button
                        key={item.id}
                        id={discoveryOptionDomId(item.id)}
                        type="button"
                        role="option"
                        aria-disabled={!itemSelectable}
                        aria-selected={isActive}
                        disabled={!itemSelectable}
                        data-active-discovery-option={isActive ? "true" : undefined}
                        onMouseEnter={() => {
                          if (itemSelectable) setActiveDiscoveryItemId(item.id);
                        }}
                        onClick={() => {
                          if (itemSelectable) insertDiscoveryItem(item);
                        }}
                        className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors ${
                          isActive
                            ? "bg-black/5 dark:bg-white/5"
                            : itemSelectable
                              ? "hover:bg-black/5 dark:hover:bg-white/5"
                              : "cursor-wait opacity-60"
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-[14px] font-medium text-black dark:text-white">
                            {item.label}
                          </span>
                          <span className="block truncate text-[12px] text-black/45 dark:text-white/45">
                            {discoveryDescriptionLabel(item, t)}
                          </span>
                        </span>
                        <span className="shrink-0 rounded-full bg-black/[0.04] px-2 py-1 text-[11px] text-black/50 dark:bg-white/[0.06] dark:text-white/50">
                          {t(`chat.discovery.badges.${discoveryBadgeLabel(item)}`, discoveryBadgeLabel(item))}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          ) : discoveryPanel.showBody ? (
            <div className="px-4 py-4 text-[14px] text-black/50 dark:text-white/50">
              {t(
                discoveryPanel.bodyKey,
                {
                  ...(discoveryPanel.bodyValues ?? {}),
                  defaultValue: discoveryPanel.bodyFallback,
                },
              )}
            </div>
          ) : null}
        </div>
      )}

      {mentionsEnabled ? (
      <button
        type="button"
        onMouseDown={(event) => event.preventDefault()}
        onClick={(event) => {
          event.stopPropagation();
          openDiscovery();
        }}
        className={`absolute left-3 top-1/2 z-20 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full text-black/45 transition-colors hover:bg-black/5 hover:text-black dark:text-white/45 dark:hover:bg-white/5 dark:hover:text-white ${
          isMentionButtonHidden ? "invisible pointer-events-none" : ""
        }`}
        aria-hidden={isMentionButtonHidden}
        tabIndex={isMentionButtonHidden ? -1 : 0}
        aria-label={t("chat.discovery.prompt", "Mention an asset or indicator")}
        aria-haspopup="listbox"
        aria-expanded={isMentionButtonHidden ? undefined : isDiscoveryOpen}
        aria-controls={!isMentionButtonHidden && isDiscoveryOpen ? "chat-discovery-listbox" : undefined}
      >
        <AtSign className="h-4 w-4" />
      </button>
      ) : (
        <div className="absolute left-3 top-1/2 z-20 -translate-y-1/2">{leadingControl}</div>
      )}

      <div className="relative flex min-w-0 flex-1 flex-col justify-center py-2 pl-14 pr-2">
        <div
          ref={editorRef}
          data-testid="chat-input"
          role="combobox"
          aria-disabled={disabled}
          aria-label={inputPlaceholder}
          aria-haspopup="listbox"
          aria-autocomplete="list"
          aria-expanded={isDiscoveryOpen}
          aria-controls={isDiscoveryOpen ? "chat-discovery-listbox" : undefined}
          aria-activedescendant={isDiscoveryOpen ? activeDiscoveryOptionId : undefined}
          contentEditable={!disabled}
          suppressContentEditableWarning
          onFocus={() => {
            setIsFocused(true);
            scheduleComposerTokenFocus();
          }}
          onBlur={() => {
            setIsFocused(false);
            clearComposerTokenFocus(editorRef.current);
          }}
          onInput={handleEditorInput}
          onSelect={scheduleComposerTokenFocus}
          onKeyUp={scheduleComposerTokenFocus}
          onMouseUp={scheduleComposerTokenFocus}
          onPaste={(e) => {
            e.preventDefault();
            handleComposerDataTransfer(e.clipboardData);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleComposerDataTransfer(e.dataTransfer);
          }}
          onKeyDown={(e) => {
            if (isDiscoveryOpen) {
              if (e.key === "Escape") {
                e.preventDefault();
                closeDiscovery();
                return;
              }
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveDiscoveryItemId((current) =>
                  nextDiscoveryItemId(selectableDiscoveryItems, current, 1),
                );
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveDiscoveryItemId((current) =>
                  nextDiscoveryItemId(selectableDiscoveryItems, current, -1),
                );
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                const action = discoveryEnterAction({
                  hasActiveItem: Boolean(activeDiscoveryItem),
                  hasComposerContent: composerHasContent,
                });
                if (action === "insert" && activeDiscoveryItem) {
                  insertDiscoveryItem(activeDiscoveryItem);
                } else if (action === "submit") {
                  closeDiscovery();
                  editorRef.current?.closest("form")?.requestSubmit();
                } else {
                  closeDiscovery();
                }
                return;
              }
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              editorRef.current?.closest("form")?.requestSubmit();
            } else if (e.key === "Backspace") {
              const current = readCurrentSegments();
              const cursor = getCaretTextOffset(editorRef.current);
              if (cursor !== null && window.getSelection()?.isCollapsed) {
                const next = deleteTokenBeforeOffset(current, cursor);
                if (next.segments !== current) {
                  e.preventDefault();
                  pendingCaretOffsetRef.current = next.offset;
                  setSegments(next.segments);
                  updateDiscoveryState(next.segments, next.offset);
                }
              }
            } else if (mentionsEnabled && e.key === "@" && !e.ctrlKey && !e.metaKey && !e.altKey) {
              buttonDiscoveryAnchorOffsetRef.current = null;
              buttonDiscoveryQueryEndOffsetRef.current = null;
              activeMentionOffsetRef.current = null;
              setIsDiscoveryOpen(true);
              setDiscoveryQuery("");
              setDiscoveryItems([]);
              setDiscoveryItemsQuery(null);
              setDiscoveryStatus("idle");
            }
          }}
          className="min-h-[1.45em] flex-1 whitespace-pre-wrap break-words border-none bg-transparent p-0 text-[16px] font-medium leading-[1.45] tracking-tight text-black outline-none dark:text-white"
        />

        {isMounted && composerIsEmpty && !isFocused && (
          <div className="pointer-events-none absolute inset-y-0 left-14 flex items-center text-[16px] font-medium leading-[1.45] tracking-tight text-gray-400 transition-opacity group-focus-within:invisible group-focus-within:opacity-0 dark:text-gray-500">
            {inputPlaceholder}
          </div>
        )}
      </div>

      <div className="flex h-14 w-14 shrink-0 self-center items-center justify-center">
        {sendDisabledReason ? (
          <Tooltip content={sendDisabledReason} side="top" delay={150}>
            <span
              data-testid="chat-send-disabled-tooltip"
              aria-disabled="true"
              aria-label={sendDisabledReason}
              tabIndex={0}
              onClick={(event) => event.stopPropagation()}
              className="inline-flex h-11 w-11 rounded-full"
            >
              <SendButton disabled={sendButtonDisabled} ariaLabel={sendButtonLabel} />
            </span>
          </Tooltip>
        ) : (
          <SendButton disabled={sendButtonDisabled} ariaLabel={sendButtonLabel} />
        )}
      </div>
    </form>
  );
}

function SendButton({ disabled, ariaLabel }: { disabled: boolean; ariaLabel: string }) {
  return (
    <button
      type="submit"
      data-testid="chat-send"
      disabled={disabled}
      aria-label={ariaLabel}
      className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-black text-white transition-opacity hover:opacity-85 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black"
    >
      <ArrowUp className="h-5 w-5 stroke-[2.5]" />
    </button>
  );
}

function normalizeDiscoverySearchText(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function rankDiscoveryItem(item: DiscoveryItem, query: string) {
  const normalized = normalizeDiscoverySearchText(query);
  const symbol = normalizeDiscoverySearchText(item.symbol ?? "");
  const label = normalizeDiscoverySearchText(item.label);
  const description = normalizeDiscoverySearchText(item.description ?? "");
  const values = [symbol, label, description].filter(Boolean);
  const exact = values.some((value) => value === normalized);
  const prefix = values.some((value) => value.startsWith(normalized));
  const contained = values.some((value) => value.includes(normalized));
  if (exact && item.type === "indicator") return 0;
  if (exact) return 1;
  if (prefix && item.type === "asset") return 2;
  if (prefix) return 3;
  if (contained && item.type === "asset") return 4;
  if (contained) return 5;
  return item.type === "asset" ? 6 : 7;
}

export function mergeDiscoveryItems(
  assets: DiscoveryItem[],
  indicators: DiscoveryItem[],
  query: string,
  limit: number,
) {
  const sortedAssets = [...assets].sort(
    (a, b) => rankDiscoveryItem(a, query) - rankDiscoveryItem(b, query),
  );
  const sortedIndicators = indicators
    .filter((item) => isSupportedDiscoveryItem(item))
    .sort((a, b) => rankDiscoveryItem(a, query) - rankDiscoveryItem(b, query));
  const merged: DiscoveryItem[] = [];
  const seen = new Set<string>();

  const push = (item: DiscoveryItem | undefined) => {
    if (!item || seen.has(item.id) || merged.length >= limit) return;
    seen.add(item.id);
    merged.push(item);
  };

  for (
    let index = 0;
    merged.length < limit &&
    (index < sortedAssets.length || index < sortedIndicators.length);
    index++
  ) {
    const indicator = sortedIndicators[index];
    const asset = sortedAssets[index];
    const indicatorRank = indicator
      ? rankDiscoveryItem(indicator, query)
      : Number.POSITIVE_INFINITY;
    const assetRank = asset
      ? rankDiscoveryItem(asset, query)
      : Number.POSITIVE_INFINITY;
    if (indicator && indicatorRank < assetRank) {
      push(indicator);
      push(asset);
    } else {
      push(asset);
      push(indicator);
    }
  }

  return merged;
}

export function discoverySectionsForDisplay(
  items: DiscoveryItem[],
  query: string,
): DiscoverySection[] {
  const visibleItems = items.filter(
    (item) => item.id && item.label && isSupportedDiscoveryItem(item),
  );
  if (visibleItems.length === 0) return [];
  if (query.trim()) {
    return [{ label: "Search results", items: visibleItems }];
  }

  const sections: DiscoverySection[] = [
    {
      label: "Popular assets",
      items: visibleItems.filter((item) => item.type === "asset"),
    },
    {
      label: "Runnable indicators",
      items: visibleItems.filter(
        (item) => item.type === "indicator" && item.support_status === "supported",
      ),
    },
  ];
  return sections.filter((section) => section.items.length > 0);
}

export function discoveryOptionDomId(id: string) {
  const safeId = id.replace(/[^A-Za-z0-9_-]+/g, "-");
  return `chat-discovery-option-${safeId}`;
}

export function shouldHideMentionButton(_isDiscoveryOpen: boolean, rawText: string) {
  return rawText.includes("@");
}

export function discoveryEnterAction({
  hasActiveItem,
  hasComposerContent,
}: {
  hasActiveItem: boolean;
  hasComposerContent: boolean;
}): "insert" | "submit" | "close" {
  if (hasActiveItem) return "insert";
  return hasComposerContent ? "submit" : "close";
}

export function nextDiscoveryItemId(
  items: DiscoveryItem[],
  currentId: string | null,
  direction: 1 | -1,
) {
  if (items.length === 0) return null;
  const currentIndex = items.findIndex((item) => item.id === currentId);
  if (currentIndex < 0) return items[0].id;
  const nextIndex = (currentIndex + direction + items.length) % items.length;
  return items[nextIndex]?.id ?? items[0].id;
}

export function discoveryResultsAreFresh(
  itemsQuery: string | null,
  activeQuery: string,
) {
  if (itemsQuery === null) return false;
  return normalizeDiscoveryFreshnessQuery(itemsQuery) === normalizeDiscoveryFreshnessQuery(activeQuery);
}

export function selectableDiscoveryItemsForQuery(
  items: DiscoveryItem[],
  itemsAreFresh: boolean,
) {
  return itemsAreFresh ? items : [];
}

function normalizeDiscoveryFreshnessQuery(value: string) {
  return value.trim().toLowerCase();
}

function discoverySectionLabelKey(label: string) {
  if (label === "Popular assets") return "chat.discovery.sections.assets";
  if (label === "Runnable indicators") return "chat.discovery.sections.indicators";
  return "chat.discovery.sections.results";
}

function discoveryBadgeLabel(item: DiscoveryItem) {
  if (item.type === "asset") return "asset";
  if (item.type === "indicator") return "indicator";
  return "indicator";
}

function isSupportedDiscoveryItem(item: DiscoveryItem) {
  return item.type !== "indicator" || item.support_status === "supported";
}

function writeSegmentsToEditor(root: HTMLDivElement | null, segments: ComposerSegment[]) {
  if (!root) return;
  root.replaceChildren();
  let offset = 0;
  for (const segment of segments) {
    if (segment.type === "text") {
      root.appendChild(document.createTextNode(segment.text));
      offset += segment.text.length;
      continue;
    }
    root.appendChild(createTokenElement(segment.token, offset));
    offset += segmentLength(segment);
  }
}

function createTokenElement(item: DiscoveryItem, start: number) {
  const token = document.createElement("span");
  token.contentEditable = "false";
  token.dataset.composerToken = "true";
  token.dataset.entityToken = "true";
  token.dataset.entityTokenFocused = "false";
  token.dataset.entityTokenKind = item.type;
  token.dataset.entityTokenSurface = "composer";
  token.dataset.tokenId = item.id;
  token.dataset.tokenStart = String(start);
  token.dataset.tokenEnd = String(start + item.insert_text.length);
  token.dataset.tokenType = item.type;
  token.dataset.tokenLabel = item.label;
  token.dataset.tokenSymbol = item.symbol ?? "";
  token.dataset.tokenAssetClass = item.asset_class ?? "";
  token.dataset.tokenDescription = displayDiscoveryDescription(item);
  token.dataset.tokenInsertText = item.insert_text;
  token.dataset.tokenProvider = item.provider;
  token.className = entityTokenClassName(item.type, "composer");

  const label = document.createElement("span");
  label.className = "truncate";
  label.textContent = item.type === "asset" ? item.insert_text : item.label;
  token.appendChild(label);
  return token;
}

function syncComposerTokenFocus(root: HTMLDivElement | null, segments: ComposerSegment[]) {
  if (!root) return;
  const selection = window.getSelection();
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
  const offset =
    selection?.isCollapsed && range && root.contains(range.startContainer)
      ? getCaretTextOffset(root)
      : null;
  const focused = offset === null ? null : composerTokenAtCaret(segments, offset);
  root.querySelectorAll<HTMLElement>("[data-composer-token]").forEach((token) => {
    token.dataset.entityTokenFocused =
      focused &&
      token.dataset.tokenStart === String(focused.start) &&
      token.dataset.tokenEnd === String(focused.end)
        ? "true"
        : "false";
  });
}

function clearComposerTokenFocus(root: HTMLDivElement | null) {
  root
    ?.querySelectorAll<HTMLElement>("[data-composer-token]")
    .forEach((token) => {
      token.dataset.entityTokenFocused = "false";
    });
}

function displayDiscoveryDescription(item: DiscoveryItem) {
  const description = item.description?.trim();
  if (!description) return item.type === "asset" ? "Asset" : "Indicator";
  if (description.toLowerCase() === "currency_pair") return "Currency Pair";
  return description.replaceAll("_", " ");
}

function discoveryDescriptionLabel(item: DiscoveryItem, t: TFunction) {
  if (item.type === "asset" && item.asset_class) {
    return t(
      `chat.discovery.descriptions.asset_classes.${item.asset_class}`,
      displayDiscoveryDescription(item),
    );
  }
  const description = displayDiscoveryDescription(item);
  if (description === "Asset") {
    return t("chat.discovery.descriptions.asset", description);
  }
  if (description === "Indicator") {
    return t("chat.discovery.descriptions.indicator", description);
  }
  if (description === "Currency Pair") {
    return t("chat.discovery.descriptions.currency_pair", description);
  }
  return description;
}

function assetClassFromDataset(value: string | undefined): DiscoveryItem["asset_class"] {
  if (value === "equity" || value === "crypto" || value === "currency_pair") {
    return value;
  }
  return null;
}

function readSegmentsFromEditor(root: HTMLDivElement | null): ComposerSegment[] {
  if (!root) return [{ type: "text", text: "" }];
  const segments: ComposerSegment[] = [];

  const appendText = (text: string) => {
    if (!text) return;
    const previous = segments.at(-1);
    if (previous?.type === "text") {
      previous.text += text;
    } else {
      segments.push({ type: "text", text });
    }
  };

  const walk = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      appendText(node.textContent ?? "");
      return;
    }
    if (!(node instanceof HTMLElement)) return;
    if (node.dataset.composerToken === "true") {
      segments.push({
        type: "token",
        token: {
          id: node.dataset.tokenId ?? "",
          type: node.dataset.tokenType === "indicator" ? "indicator" : "asset",
          label: node.dataset.tokenLabel ?? node.dataset.tokenInsertText ?? "",
          symbol: node.dataset.tokenSymbol || null,
          asset_class: assetClassFromDataset(node.dataset.tokenAssetClass),
          description: node.dataset.tokenDescription || null,
          insert_text: node.dataset.tokenInsertText ?? node.textContent ?? "",
          provider: node.dataset.tokenProvider ?? "",
        },
      });
      return;
    }
    if (node.tagName === "BR") {
      appendText("\n");
      return;
    }
    node.childNodes.forEach(walk);
    if (node !== root && (node.tagName === "DIV" || node.tagName === "P")) {
      appendText("\n");
    }
  };

  root.childNodes.forEach(walk);
  return segments.length > 0 ? segments : [{ type: "text", text: "" }];
}

function getCaretTextOffset(root: HTMLDivElement | null) {
  if (!root) return null;
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer)) return null;
  return countOffset(root, range.startContainer, range.startOffset);
}

function countOffset(root: Node, target: Node, targetOffset: number) {
  if (root === target) {
    let rootOffset = 0;
    for (let index = 0; index < targetOffset; index += 1) {
      const child = root.childNodes[index];
      if (child) rootOffset += nodeTextLength(child);
    }
    return rootOffset;
  }
  let offset = 0;
  let found = false;

  const walk = (node: Node) => {
    if (found) return;
    if (node === target) {
      if (node.nodeType === Node.TEXT_NODE) {
        offset += targetOffset;
      } else {
        node.childNodes.forEach((child, index) => {
          if (index < targetOffset) offset += nodeTextLength(child);
        });
      }
      found = true;
      return;
    }
    if (containsNode(node, target)) {
      node.childNodes.forEach(walk);
      return;
    }
    offset += nodeTextLength(node);
  };

  root.childNodes.forEach(walk);
  return offset;
}

function nodeTextLength(node: Node): number {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent?.length ?? 0;
  if (node instanceof HTMLElement && node.dataset.composerToken === "true") {
    return node.dataset.tokenInsertText?.length ?? node.textContent?.length ?? 0;
  }
  if (node instanceof HTMLElement && node.tagName === "BR") return 1;
  let length = 0;
  node.childNodes.forEach((child) => {
    length += nodeTextLength(child);
  });
  return length;
}

function containsNode(parent: Node, child: Node) {
  return parent === child || parent.contains(child);
}

function setCaretTextOffset(root: HTMLDivElement | null, targetOffset: number) {
  if (!root) return;
  root.focus();
  const selection = window.getSelection();
  if (!selection) return;
  const range = document.createRange();
  let cursor = 0;
  let placed = false;

  const walk = (node: Node) => {
    if (placed) return;
    if (node.nodeType === Node.TEXT_NODE) {
      const length = node.textContent?.length ?? 0;
      if (cursor + length >= targetOffset) {
        range.setStart(node, Math.max(0, targetOffset - cursor));
        placed = true;
        return;
      }
      cursor += length;
      return;
    }
    if (node instanceof HTMLElement && node.dataset.composerToken === "true") {
      const length = segmentLength({
        type: "token",
        token: {
          id: node.dataset.tokenId ?? "",
          type: node.dataset.tokenType === "indicator" ? "indicator" : "asset",
          label: node.dataset.tokenLabel ?? "",
          symbol: node.dataset.tokenSymbol || null,
          asset_class: assetClassFromDataset(node.dataset.tokenAssetClass),
          description: node.dataset.tokenDescription || null,
          insert_text: node.dataset.tokenInsertText ?? node.textContent ?? "",
          provider: node.dataset.tokenProvider ?? "",
        },
      });
      if (cursor + length >= targetOffset) {
        range.setStartAfter(node);
        placed = true;
        return;
      }
      cursor += length;
      return;
    }
    node.childNodes.forEach(walk);
  };

  root.childNodes.forEach(walk);
  if (!placed) {
    range.selectNodeContents(root);
    range.collapse(false);
  }
  selection.removeAllRanges();
  selection.addRange(range);
}
