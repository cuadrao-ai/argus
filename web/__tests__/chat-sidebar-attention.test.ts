import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

describe("chat sidebar activity ownership", () => {
  test("renders selected-row markers in the protected left lane while preserving quick-jump geometry", () => {
    const sidebar = readFileSync(
      join(root, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );
    const rowClassStart = sidebar.indexOf("className={`group relative flex w-full");
    const rowClassEnd = sidebar.indexOf("}`}", rowClassStart);
    const rowClassBlock = sidebar.slice(rowClassStart, rowClassEnd);
    const attentionLaneStart = sidebar.indexOf(
      'className="flex h-6 w-11 flex-shrink-0 items-center justify-center"',
    );
    const attentionLaneEnd = sidebar.indexOf("</div>", attentionLaneStart);
    const attentionLaneBlock = sidebar.slice(
      attentionLaneStart,
      attentionLaneEnd,
    );

    expect(rowClassStart).toBeGreaterThan(-1);
    expect(attentionLaneStart).toBeGreaterThan(-1);
    expect(rowClassBlock).toContain("isActiveConversation");
    expect(rowClassBlock).not.toContain("bg-[#7da0ca]");
    expect(sidebar).not.toContain("attentionConversationIds");
    expect(sidebar).not.toContain("EMPTY_ATTENTION_IDS");
    expect(sidebar).not.toContain("hasConversationAttention");
    expect(sidebar).not.toContain("data-has-attention");
    expect(sidebar).toContain("aria-label={rowAriaLabel}");
    expect(sidebar).toContain("presentation={itemActivityPresentation}");
    expect(attentionLaneBlock).toContain("ConversationActivityIndicator");
    expect(attentionLaneBlock).not.toContain("isActiveConversation &&");
    expect(attentionLaneBlock).not.toContain("QuickJumpBadge");
    expect(sidebar).toContain("data-quick-jump-hint={quickJumpNumber}");
    expect(sidebar.indexOf("quickJumpHint={quickJumpHint}", attentionLaneEnd))
      .toBeGreaterThan(attentionLaneEnd);
  });

  test("uses existing selectors for row and collapsed aggregate precedence", () => {
    const sidebar = readFileSync(
      join(root, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );

    expect(sidebar).toContain("useConversationActivityPresentation");
    expect(sidebar).toContain("selectPresentation(itemConversationId)");
    expect(sidebar).toContain("selectOperationLabel(itemConversationId)");
    expect(sidebar).toContain(
      "conversationActivityLabelDescriptor(\n                            itemActivityPresentation,\n                            itemOperationLabel,",
    );
    expect(sidebar).toContain("selectAggregatePresentation(loadedConversationIds)");
    expect(sidebar).toContain(
      "activityPresentation={aggregateActivityPresentation}",
    );
  });
});
