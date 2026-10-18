import { expect, test } from "@playwright/test";
import { activity, backtestJob, backtestJobMessage, recoveredClarificationRailTranscript, installActivityFixture, recentRow, openRecents, openConversation, refreshActivity, requiredBox, captureEvidence } from "./support/conversation-activity-fixture";

test("ordinary work remains owned by A after switching to B and clears only at visible latest", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page);
  await page.goto("/chat?conversation=activity-a");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await openRecents(page);

  await page.getByTestId("chat-input").fill("Keep working in A");
  await page.getByTestId("chat-send").click();
  await expect.poll(() => fixture.pendingStreams.has("activity-a")).toBe(true);
  await expect(
    recentRow(page, "activity-a").locator(
      '[data-conversation-activity="working"]',
    ),
  ).toBeVisible();

  await openConversation(page, "activity-b");
  await expect(page.getByTestId("chat-input")).toHaveAttribute(
    "aria-disabled",
    "false",
  );
  await captureEvidence(
    page,
    "01-en-desktop-light-working-a-viewing-b.png",
  );
  fixture.settleOrdinary("activity-a");

  const aRow = recentRow(page, "activity-a");
  await expect(
    aRow.locator('[data-conversation-activity="new_activity"]'),
  ).toBeVisible();
  await expect(page.getByText("Terminal response for activity-a")).toHaveCount(0);
  await captureEvidence(
    page,
    "02-en-desktop-light-settled-a-unread.png",
  );

  await openConversation(page, "activity-a");
  await expect(page.getByText("Terminal response for activity-a")).toBeVisible();
  await expect
    .poll(() => fixture.activityMutations)
    .toContainEqual({
      conversationId: "activity-a",
      body: {
        action: "mark_read",
        through_attention_cursor: "chat_turn:activity-a-1",
      },
    });
  await expect(aRow.locator("[data-conversation-activity]")).toHaveCount(0);
  expect(fixture.unexpectedRequests).toEqual([]);
});

for (const firstToSettle of ["activity-a", "activity-b"] as const) {
  test(`simultaneous A and B requests stay isolated when ${firstToSettle} settles first`, async ({
    page,
  }) => {
    const fixture = await installActivityFixture(page);
    await page.goto("/chat?conversation=activity-a");
    await openRecents(page);
    await page.getByTestId("chat-input").fill("Start A");
    await page.getByTestId("chat-send").click();
    await expect.poll(() => fixture.pendingStreams.has("activity-a")).toBe(true);

    await openConversation(page, "activity-b");
    await page.getByTestId("chat-input").fill("Start B");
    await page.getByTestId("chat-send").click();
    await expect.poll(() => fixture.pendingStreams.has("activity-b")).toBe(true);
    await expect(
      recentRow(page, "activity-a").locator(
        '[data-conversation-activity="working"]',
      ),
    ).toBeVisible();
    await expect(
      recentRow(page, "activity-b").locator(
        '[data-conversation-activity="working"]',
      ),
    ).toBeVisible();
    if (firstToSettle === "activity-a") {
      await captureEvidence(
        page,
        "03-en-desktop-light-simultaneous-a-b-working.png",
      );
    }

    fixture.settleOrdinary(firstToSettle);
    const other =
      firstToSettle === "activity-a" ? "activity-b" : "activity-a";
    await expect(
      recentRow(page, other).locator('[data-conversation-activity="working"]'),
    ).toBeVisible();
    await expect(page).toHaveURL(/conversation=activity-b(?:&|$)/);
    await expect(page.getByText("Terminal response for activity-a")).toHaveCount(
      0,
    );

    fixture.settleOrdinary(other);
    await expect(
      recentRow(page, "activity-a").locator(
        '[data-conversation-activity="new_activity"]',
      ),
    ).toBeVisible();
    await expect(page).toHaveURL(/conversation=activity-b(?:&|$)/);
    await expect(page.getByText("Terminal response for activity-a")).toHaveCount(0);
    expect(fixture.unexpectedRequests).toEqual([]);
  });
}

test("durable backtest stays working through queued, running, and checking before canonical result hydration", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page);
  fixture.stageBacktest("activity-a", "queued");
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page);
  await expect(page.getByText("Backtest queued", { exact: true })).toBeVisible();
  await openConversation(page, "activity-b");

  fixture.stageBacktest("activity-a", "running");
  await refreshActivity(page, fixture);
  await expect(
    recentRow(page, "activity-a").locator(
      '[data-conversation-activity="working"]',
    ),
  ).toBeVisible();

  fixture.stageBacktest("activity-a", "checking");
  await refreshActivity(page, fixture);
  await expect(recentRow(page, "activity-a")).toHaveAccessibleName(
    /Activity A\. Checking status\./,
  );
  await expect(
    recentRow(page, "activity-a").locator(
      '[data-conversation-activity="new_activity"]',
    ),
  ).toHaveCount(0);
  await captureEvidence(page, "04-en-desktop-light-backtest-checking.png");

  fixture.stageBacktest("activity-a", "ready");
  await refreshActivity(page, fixture);
  await expect(
    recentRow(page, "activity-a").locator(
      '[data-conversation-activity="new_activity"]',
    ),
  ).toBeVisible();
  await openConversation(page, "activity-a");
  await expect(page.getByText("Simulation Complete", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Buy and hold", exact: true }),
  ).toBeVisible();
  expect(fixture.unexpectedRequests).toEqual([]);
});

test("completion while scrolled up keeps position and evolves the single Jump to latest control", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page, {
    longTranscripts: ["activity-a"],
  });
  fixture.setActivity("activity-a", activity("running"));
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page);
  const transcript = page.getByTestId("conversation-transcript-region");
  await expect(transcript.getByText(/Transcript activity-a message 43/)).toBeVisible();
  const scrollTop = await transcript.evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event("scroll"));
    return element.scrollTop;
  });
  const workingJump = page.getByRole("button", {
    name: "Jump to latest; Argus is working below",
  });
  await expect(workingJump).toBeVisible();
  await captureEvidence(page, "05-en-desktop-light-jump-working-below.png");

  fixture.setActivity(
    "activity-a",
    activity("idle", "new_activity", "chat_turn:activity-a-complete"),
  );
  await refreshActivity(page, fixture);
  await expect
    .poll(() => transcript.evaluate((element) => element.scrollTop))
    .toBeCloseTo(scrollTop, 0);
  const unreadJump = page.getByRole("button", { name: "Jump to new activity" });
  await expect(unreadJump).toBeVisible();
  await expect(page.getByRole("button", { name: /Jump to/ })).toHaveCount(1);
  await captureEvidence(page, "06-en-desktop-light-jump-unread-below.png");
  await unreadJump.focus();
  await unreadJump.press("Enter");
  await expect
    .poll(() => fixture.activityMutations)
    .toContainEqual({
      conversationId: "activity-a",
      body: {
        action: "mark_read",
        through_attention_cursor: "chat_turn:activity-a-complete",
      },
    });
  expect(fixture.unexpectedRequests).toEqual([]);
});

test("restored older scroll and an older message anchor retain unread until latest", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page, {
    longTranscripts: ["activity-a", "activity-c"],
  });
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page);
  const transcript = page.getByTestId("conversation-transcript-region");
  await expect(transcript.getByText(/Transcript activity-a message 43/)).toBeVisible();
  await transcript.evaluate((element) => {
    element.scrollTop = 180;
    element.dispatchEvent(new Event("scroll"));
  });
  await openConversation(page, "activity-b");
  fixture.setActivity(
    "activity-a",
    activity("idle", "new_activity", "chat_turn:activity-a-restored"),
  );
  await refreshActivity(page, fixture);
  await openConversation(page, "activity-a");
  await expect(page.getByRole("button", { name: "Jump to new activity" })).toBeVisible();
  await captureEvidence(
    page,
    "07-en-desktop-light-restored-scroll-unread.png",
  );
  expect(
    fixture.activityMutations.some(
      (mutation) => mutation.conversationId === "activity-a",
    ),
  ).toBe(false);

  fixture.setActivity(
    "activity-c",
    activity("idle", "new_activity", "chat_turn:activity-c-anchor"),
  );
  await page.goto(
    "/chat?conversation=activity-c&message=activity-c-assistant-2",
  );
  await expect(page).toHaveURL(
    /conversation=activity-c&message=activity-c-assistant-2/,
  );
  await expect(
    transcript.locator('[data-message-id="activity-c-assistant-2"]'),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Jump to new activity" })).toBeVisible();
  await captureEvidence(page, "08-en-desktop-light-anchor-unread.png");
  expect(
    fixture.activityMutations.some(
      (mutation) => mutation.conversationId === "activity-c",
    ),
  ).toBe(false);
  expect(fixture.unexpectedRequests).toEqual([]);
});

test("row and header menus toggle durable unread without reordering or same-view self-clear", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page);
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page);
  const rowsBefore = await page
    .locator('[role="button"][data-conversation-id]')
    .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-conversation-id")));
  const bRow = recentRow(page, "activity-b");
  const bTitle = bRow.getByText("Activity B", { exact: true });
  const rowBefore = await requiredBox(bRow);
  const titleBefore = await requiredBox(bTitle);
  const more = bRow.getByRole("button", { name: "More" });
  await more.focus();
  const moreBox = await requiredBox(more);
  expect(moreBox.width).toBeGreaterThanOrEqual(44);
  expect(moreBox.height).toBeGreaterThanOrEqual(44);
  await more.press("Enter");
  await expect(page.getByRole("menuitem").first()).toHaveText("Mark as unread");
  await captureEvidence(
    page,
    "09-en-desktop-light-recents-menu-mark-unread.png",
  );
  await page.getByRole("menuitem", { name: "Mark as unread" }).click();
  await expect(
    bRow.locator('[data-conversation-activity="manual_unread"]'),
  ).toBeVisible();
  const rowAfter = await requiredBox(bRow);
  const titleAfter = await requiredBox(bTitle);
  expect(rowAfter.y).toBeCloseTo(rowBefore.y, 1);
  expect(titleAfter.x).toBeCloseTo(titleBefore.x, 1);
  expect(
    await page
      .locator('[role="button"][data-conversation-id]')
      .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-conversation-id"))),
  ).toEqual(rowsBefore);
  await captureEvidence(
    page,
    "10-en-desktop-light-recents-manual-unread-no-reorder.png",
  );

  const headerMenu = page.getByRole("button", { name: "Chat options" });
  await headerMenu.click();
  await expect(page.getByRole("menuitem").first()).toHaveText("Mark as unread");
  await captureEvidence(
    page,
    "11-en-desktop-light-header-menu-mark-unread.png",
  );
  await page.getByRole("menuitem", { name: "Mark as unread" }).click();
  const aRow = recentRow(page, "activity-a");
  await expect(
    aRow.locator('[data-conversation-activity="manual_unread"]'),
  ).toBeVisible();
  await refreshActivity(page, fixture);
  await expect(
    aRow.locator('[data-conversation-activity="manual_unread"]'),
  ).toBeVisible();
  await captureEvidence(
    page,
    "12-en-desktop-light-header-manual-unread.png",
  );

  await headerMenu.click();
  await expect(page.getByRole("menuitem").first()).toHaveText("Mark as read");
  await captureEvidence(
    page,
    "13-en-desktop-light-header-menu-mark-read.png",
  );
  await page.getByRole("menuitem", { name: "Mark as read" }).click();
  await expect(aRow.locator("[data-conversation-activity]")).toHaveCount(0);
  await captureEvidence(page, "14-en-desktop-light-header-marked-read.png");

  await bRow.getByRole("button", { name: "More" }).click();
  await page.keyboard.press("Escape");
  await expect(bRow.getByRole("button", { name: "More" })).toBeFocused();
  expect(fixture.unexpectedRequests).toEqual([]);
});

test("expanded, collapsed, Quick Peek, selected, dark, and reduced-motion projections share one precedence", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const fixture = await installActivityFixture(page, {
    activities: {
      "activity-a": activity("running", "new_activity", "cursor-a"),
      "activity-b": activity("idle", "new_activity", "cursor-b"),
      "activity-c": activity("idle", "manual_unread", "cursor-c"),
      "activity-d": activity("idle", "needs_input", "cursor-d"),
      "activity-e": activity("idle", "needs_attention", "cursor-e"),
      "activity-f": activity("checking", "none", null, "backtest_job"),
    },
    darkMode: true,
    longTranscripts: ["activity-a"],
  });
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page);
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(recentRow(page, "activity-a")).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(recentRow(page, "activity-a")).toHaveAccessibleName(
    "Activity A. Working.",
  );
  await expect(recentRow(page, "activity-d")).toHaveAccessibleName(
    "Activity D. Needs your input.",
  );
  await expect(recentRow(page, "activity-e")).toHaveAccessibleName(
    "Activity E. Needs attention.",
  );
  const ring = recentRow(page, "activity-a").locator(
    '[data-conversation-activity="working"] svg',
  );
  expect(await ring.evaluate((node) => getComputedStyle(node).animationName)).toBe(
    "none",
  );
  await captureEvidence(
    page,
    "15-en-desktop-dark-reduced-expanded-selected.png",
  );

  await page.keyboard.press("Meta+Shift+Comma");
  const peek = page.getByRole("dialog", { name: "Recents" });
  await expect(
    peek.getByRole("button", { name: "Activity A. Working." }),
  ).toBeVisible();
  await expect(
    peek.getByRole("button", { name: "Activity E. Needs attention." }),
  ).toBeVisible();
  await captureEvidence(page, "16-en-desktop-dark-reduced-quick-peek.png");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Collapse", exact: true }).click();
  const recents = page.getByRole("button", { name: "Recents" });
  await expect(
    recents.locator('[data-sidebar-activity-overlay="true"]'),
  ).toBeVisible();
  await expect(
    recents.locator('[data-conversation-activity="working"]'),
  ).toBeVisible();
  await captureEvidence(
    page,
    "17-en-desktop-dark-reduced-collapsed-aggregate.png",
  );

  const transcript = page.getByTestId("conversation-transcript-region");
  await transcript.evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event("scroll"));
  });
  const workingJump = page.getByRole("button", {
    name: "Jump to latest; Argus is working below",
  });
  await expect(workingJump).toBeVisible();
  const dotAnimations = await workingJump
    .locator("[data-working-dot]")
    .evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node).animationName),
    );
  expect(dotAnimations).toEqual(["none", "none", "none"]);
  await captureEvidence(
    page,
    "18-en-desktop-dark-reduced-static-working-below.png",
  );
  expect(fixture.unexpectedRequests).toEqual([]);
});

test.describe("390px coarse pointer", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });

  test("mobile Recents keeps the touch-safe owner menu and typed activity labels", async ({
    page,
  }) => {
    const fixture = await installActivityFixture(page, {
      activities: {
        "activity-a": activity("running"),
        "activity-b": activity("idle", "new_activity", "cursor-b"),
      },
      language: "es-419",
    });
    await page.goto("/chat?conversation=activity-a");
    await openRecents(page, "es-419");
    await expect(page.locator("html")).toHaveAttribute("lang", "es-419");
    await expect(recentRow(page, "activity-a")).toHaveAccessibleName(
      "Activity A. En curso.",
    );
    await expect(recentRow(page, "activity-b")).toHaveAccessibleName(
      "Activity B. Actividad nueva.",
    );
    const more = recentRow(page, "activity-b").getByRole("button", {
      name: "Más",
    });
    await expect(more).toBeVisible();
    const box = await requiredBox(more);
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await captureEvidence(page, "19-es-mobile-coarse-recents.png");
    expect(fixture.unexpectedRequests).toEqual([]);
  });
});

test("typed needs-input, attention, canceled, expired, and checking states do not alter the activity rail", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page, {
    activities: {
      "activity-a": activity(),
      "activity-b": activity("idle", "needs_input", "cursor-b"),
      "activity-c": activity("idle", "needs_attention", "cursor-c"),
      "activity-d": activity("idle", "needs_attention", "cursor-d"),
      "activity-e": activity("checking", "none", null, "backtest_job"),
    },
    railTranscript: "activity-a",
  });
  const canceled = backtestJob("activity-c", "canceled");
  fixture.jobs["activity-c"] = canceled;
  fixture.messages["activity-c"] = [
    backtestJobMessage("activity-c", canceled),
  ];
  const expired = backtestJob("activity-d", "expired");
  fixture.jobs["activity-d"] = expired;
  fixture.messages["activity-d"] = [
    backtestJobMessage("activity-d", expired),
  ];
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page);
  await expect(recentRow(page, "activity-b")).toHaveAccessibleName(
    "Activity B. Needs your input.",
  );
  await expect(recentRow(page, "activity-c")).toHaveAccessibleName(
    "Activity C. Needs attention.",
  );
  await expect(recentRow(page, "activity-d")).toHaveAccessibleName(
    "Activity D. Needs attention.",
  );
  await expect(recentRow(page, "activity-e")).toHaveAccessibleName(
    "Activity E. Checking status.",
  );
  await expect(page.getByTestId("conversation-activity-rail")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Conversation activity" }),
  ).toBeVisible();
  await expect(
    page
      .getByTestId("conversation-activity-rail")
      .locator("[data-conversation-activity]"),
  ).toHaveCount(0);
  await captureEvidence(
    page,
    "20-en-desktop-light-typed-attention-checking.png",
  );
  await openConversation(page, "activity-c");
  await expect(
    page.getByText("Backtest not completed", { exact: true }),
  ).toBeVisible();
  await openConversation(page, "activity-d");
  await expect(
    page.getByText("Backtest not completed", { exact: true }),
  ).toBeVisible();
  expect(fixture.unexpectedRequests).toEqual([]);
});

for (const [language, screenshot, completedLabel] of [
  [
    "en",
    "issue-337-en.png",
    "Backtest finished — AAPL · Buy and hold",
  ],
  [
    "es-419",
    "issue-337-es-419.png",
    "Backtest terminado — AAPL · Buy and hold",
  ],
] as const) {
  test(`resolved clarification clears its rail marker in ${language}`, async ({
    page,
  }) => {
    const fixture = await installActivityFixture(page, {
      accountKind: "guest",
      language,
      railTranscript: "activity-a",
    });
    fixture.messages["activity-a"] = recoveredClarificationRailTranscript(
      "activity-a",
    );

    await page.goto("/chat?conversation=activity-a");

    await expect(page.getByTestId("guest-temporary-notice")).toBeVisible();
    const rail = page.getByTestId("conversation-activity-rail");
    await expect(rail).toBeVisible();
    await expect(rail.getByRole("button")).toHaveCount(1);
    await expect(
      rail.getByRole("button", { name: completedLabel }),
    ).toBeVisible();
    await captureEvidence(page, screenshot);
    expect(fixture.unexpectedRequests).toEqual([]);
  });
}

test("Spanish desktop exposes the complete typed activity vocabulary", async ({
  page,
}) => {
  const fixture = await installActivityFixture(page, {
    activities: {
      "activity-a": activity("running"),
      "activity-b": activity("idle", "new_activity", "cursor-b"),
      "activity-c": activity("idle", "manual_unread", "cursor-c"),
      "activity-d": activity("idle", "needs_input", "cursor-d"),
      "activity-e": activity("idle", "needs_attention", "cursor-e"),
      "activity-f": activity("checking", "none", null, "backtest_job"),
    },
    language: "es-419",
  });
  await page.goto("/chat?conversation=activity-a");
  await openRecents(page, "es-419");
  await expect(page.locator("html")).toHaveAttribute("lang", "es-419");
  await expect(recentRow(page, "activity-a")).toHaveAccessibleName(
    "Activity A. En curso.",
  );
  await expect(recentRow(page, "activity-b")).toHaveAccessibleName(
    "Activity B. Actividad nueva.",
  );
  await expect(recentRow(page, "activity-c")).toHaveAccessibleName(
    "Activity C. Marcada como no leída.",
  );
  await expect(recentRow(page, "activity-d")).toHaveAccessibleName(
    "Activity D. Necesita tu respuesta.",
  );
  await expect(recentRow(page, "activity-e")).toHaveAccessibleName(
    "Activity E. Necesita atención.",
  );
  await page.getByRole("button", { name: "Mostrar más en Hoy" }).click();
  await expect(recentRow(page, "activity-f")).toHaveAccessibleName(
    "Activity F. Consultando el estado.",
  );
  await captureEvidence(page, "21-es-desktop-activity-labels.png");
  expect(fixture.unexpectedRequests).toEqual([]);
});

for (const language of ["en", "es-419"] as const) {
  test(`second tab loads the saved reply on completion without duplicating the sender (${language})`, async ({ context, page: tabA }) => {
    const fixture = await installActivityFixture(context, { language });
    const tabB = await context.newPage();
    const reply = "Terminal response for activity-a";
    const prompt = language === "en" ? "Explain compound interest" : "Explica el interés compuesto";
    const reads = { a: 0, b: 0 };
    for (const [tab, key] of [[tabA, "a"], [tabB, "b"]] as const) {
      tab.on("request", (request) => {
        if (request.url().includes("/conversations/activity-a/messages")) reads[key] += 1;
      });
      await tab.goto("/chat?conversation=activity-a");
      await expect(tab.getByText("Transcript activity-a message 0", { exact: true })).toBeVisible();
    }
    await tabA.getByTestId("chat-input").fill(prompt);
    await tabA.getByTestId("chat-send").click();
    await expect.poll(() => fixture.pendingStreams.has("activity-a")).toBe(true);
    // Use the existing focus refresh to learn that work started, then let its
    // ordinary activity poll discover completion. No message reload or focus
    // event is injected after settlement.
    await refreshActivity(tabB, fixture);
    await expect(tabB.getByTestId("conversation-activity-announcement")).toContainText(
      language === "en" ? "Argus is working" : "Argus está trabajando",
    );
    const before = { ...reads };
    fixture.settleOrdinary("activity-a");
    try {
      await expect(tabA.getByText(reply, { exact: true })).toHaveCount(1);
      await expect(tabB.getByText(reply, { exact: true })).toBeVisible({ timeout: 10_000 });
      for (const tab of [tabA, tabB]) {
        await expect(tab.getByText(reply, { exact: true })).toHaveCount(1);
        await expect(tab.getByText(prompt, { exact: true })).toHaveCount(1);
      }
      expect(reads.a).toBe(before.a);
      expect(reads.b).toBe(before.b + 1);
      // A repeated canonical projection must not load or append again.
      await refreshActivity(tabB, fixture);
      expect(reads.b).toBe(before.b + 1);
      expect(fixture.unexpectedRequests).toEqual([]);
    } finally {
      await captureEvidence(tabA, `598-${language}-tab-a.png`);
      await captureEvidence(tabB, `598-${language}-tab-b.png`);
    }
  });
}
