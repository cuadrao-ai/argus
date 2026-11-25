import { expect, test, type Locator } from "@playwright/test";
import { expectOneCanonicalCard } from "./auth-card-assertions";

type Frame = { card: number; rows: Record<string, number> };
type StepChange = { before: number; midway: number | null; afterOneFrame: number; transitions: string[]; frames: Frame[] };

const SAMPLE_MS = [0, 20, 40, 70, 110, 160, 280];

async function changeStep(button: Locator): Promise<StepChange> {
  return button.evaluate(async (el: HTMLButtonElement, sampleMs: number[]) => {
    const card = el.closest<HTMLElement>("[data-auth-entry-step]")!;
    const height = () => card.getBoundingClientRect().height;
    const rowName = (row: Element) => row.querySelector('input[name="username"]') ? "summary"
      : row.querySelector('input[type="email"]') ? "email"
      : row.querySelector('input[type="password"]') ? "password" : "names";
    const frame = (): Frame => ({
      card: height(),
      rows: Object.fromEntries([...card.querySelectorAll("[data-open]")].map(row => [rowName(row), row.getBoundingClientRect().height])),
    });
    const before = height();
    el.click();
    await Promise.resolve();
    const animations = card.getAnimations({ subtree: true });
    const transitions = animations.filter(
      (animation): animation is CSSTransition => animation instanceof CSSTransition &&
        animation.effect instanceof KeyframeEffect && animation.effect.target instanceof HTMLElement &&
        animation.effect.target.matches("[data-open]"),
    );
    let midway: number | null = null;
    const frames: Frame[] = [];
    if (transitions.length > 0) {
      for (const animation of animations) animation.pause();
      for (const animation of animations) animation.currentTime = Number(transitions[0].effect!.getTiming().duration) / 2;
      midway = height();
      for (const t of sampleMs) {
        for (const animation of animations) animation.currentTime = t;
        frames.push(frame());
      }
      for (const animation of animations) animation.play();
    }
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    return { before, midway, afterOneFrame: height(), transitions: transitions.map(t => t.transitionProperty), frames };
  }, SAMPLE_MS);
}

function expectOnlyThePasswordSlides({ frames }: StepChange, from: number, to: number, shown: string, hidden: string) {
  expect(frames).toHaveLength(SAMPLE_MS.length);
  const end = frames.at(-1)!;
  expect(end.card).toBeCloseTo(to, 0);
  expect(end.rows[shown]).toBeGreaterThan(0);
  for (const [index, { card, rows }] of frames.entries()) {
    const at = `${SAMPLE_MS[index]}ms in`;
    expect(rows[shown], `${shown} at full height ${at}`).toBeCloseTo(end.rows[shown], 1);
    expect(rows[hidden], `${hidden} gone ${at}`).toBe(0);
    for (const name of Object.keys(rows).filter(name => name !== "password")) {
      expect(rows[name], `${name} holds its height ${at}`).toBeCloseTo(end.rows[name], 1);
    }
    expect(card, `card within the two step heights ${at}`).toBeGreaterThanOrEqual(Math.min(from, to) - 0.5);
    expect(card, `card within the two step heights ${at}`).toBeLessThanOrEqual(Math.max(from, to) + 0.5);
    if (index > 0) {
      expect(Math.sign(to - from) * (card - frames[index - 1].card), `card moves one way ${at}`).toBeGreaterThanOrEqual(-0.5);
    }
  }
}

type RapidFrame = { t: number; click: boolean; card: number; summary: number; email: number; password: number; opacity: number };

test("rapid Continuar and Editar reverse from wherever the card is, with no cut text", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/v1/me", route => route.fulfill({ status: 401, json: { detail: "unauthorized" } }));
  await page.goto("/login");
  const card = page.locator("[data-auth-entry-step]");
  await card.locator('input[type="email"]').fill("demo@example.test");
  await page.evaluate(() => document.fonts.ready);

  const frames = await card.evaluate(el => new Promise<RapidFrame[]>(resolve => {
    const rowOf = (selector: string) => el.querySelector(selector)!.closest<HTMLElement>("[data-open]")!;
    const [summary, email, password] = ['input[name="username"]', 'input[type="email"]', 'input[autocomplete="current-password"]'].map(rowOf);
    const continuar = el.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    const editar = summary.querySelector<HTMLButtonElement>("button")!;
    const clicks = [continuar, editar, continuar, editar, continuar];
    const frames: RapidFrame[] = [];
    let clicked = false;
    const start = performance.now();
    const tick = (now: number) => {
      if (frames.length === 0) clicks.forEach((button, index) => setTimeout(() => { clicked = true; button.click(); }, index * 120));
      frames.push({
        t: now - start, click: clicked, card: el.getBoundingClientRect().height,
        summary: summary.getBoundingClientRect().height, email: email.getBoundingClientRect().height,
        password: password.getBoundingClientRect().height, opacity: Number(getComputedStyle(password).opacity),
      });
      clicked = false;
      if (now - start < 4 * 120 + 700) requestAnimationFrame(tick); else resolve(frames);
    };
    requestAnimationFrame(tick);
  }));

  const full = { summary: frames.at(-1)!.summary, email: frames[0].email, password: frames.at(-1)!.password };
  expect(full.summary).toBeGreaterThan(0);
  expect(full.email).toBeGreaterThan(0);
  expect(frames.filter(frame => frame.click)).toHaveLength(5);
  for (const [index, frame] of frames.entries()) {
    const at = `${Math.round(frame.t)}ms in`;
    expect(Math.min(frame.summary, Math.abs(frame.summary - full.summary)), `summary whole or gone ${at}`).toBeLessThan(0.5);
    expect(Math.min(frame.email, Math.abs(frame.email - full.email)), `email whole or gone ${at}`).toBeLessThan(0.5);
    if (frame.password > 0.5 && frame.password < full.password * 0.95) expect(frame.opacity, `partly open password is faded ${at}`).toBeLessThan(1);
    if (index === 0) continue;
    const previous = frames[index - 1];
    if (frame.click) expect(Math.abs(frame.card - previous.card), `card holds on the click frame ${at}`).toBeLessThan(0.5);
    expect(Math.abs(frame.card - previous.card) / Math.max(frame.t - previous.t, 1), `card speed ${at}`).toBeLessThan(2);
  }
});

for (const reducedMotion of ["no-preference", "reduce"] as const) {
  test(`sign-in card grows for the password step and slides back with ${reducedMotion} motion`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion });
    await page.route("**/api/v1/me", route => route.fulfill({ status: 401, json: { detail: "unauthorized" } }));
    await page.goto("/login");
    const card = page.locator("[data-auth-entry-step]");
    const email = card.locator('input[type="email"]');
    const password = card.locator('input[autocomplete="current-password"]');
    const submit = card.locator('button[type="submit"]');
    await email.fill("demo@example.test");
    await page.evaluate(() => document.fonts.ready);
    const height = () => card.evaluate(el => el.getBoundingClientRect().height);
    const settle = () => card.evaluate(el => Promise.all(el.getAnimations({ subtree: true }).map(a => a.finished)));

    const emailStepHeight = await height();
    expect(emailStepHeight).toBeGreaterThan(0);
    await expect(password).toBeHidden();
    await expectOneCanonicalCard(card);

    const forward = await changeStep(submit);
    await expect(password).toBeFocused();
    await settle();
    const passwordStepHeight = await height();
    expect(passwordStepHeight).toBeGreaterThan(emailStepHeight);
    await expect(email).toBeHidden();
    await expectOneCanonicalCard(card);

    const back = await changeStep(card.getByRole("button", { name: "Editar" }));
    await expect(email).toBeFocused();
    await settle();
    expect(await height()).toBe(emailStepHeight);
    await expect(password).toBeHidden();

    expect(forward.before).toBe(emailStepHeight);
    expect(back.before).toBe(passwordStepHeight);
    if (reducedMotion === "reduce") {
      expect(forward.transitions).toEqual([]);
      expect(back.transitions).toEqual([]);
      expect(forward.afterOneFrame).toBe(passwordStepHeight);
      expect(back.afterOneFrame).toBe(emailStepHeight);
    } else {
      expect(forward.transitions).toContain("grid-template-rows");
      expect(back.transitions).toContain("grid-template-rows");
      expect(forward.midway).toBeGreaterThan(emailStepHeight);
      expect(forward.midway).toBeLessThan(passwordStepHeight);
      expect(back.midway).toBeGreaterThan(emailStepHeight);
      expect(back.midway).toBeLessThan(passwordStepHeight);
      expectOnlyThePasswordSlides(forward, emailStepHeight, passwordStepHeight, "summary", "email");
      expectOnlyThePasswordSlides(back, passwordStepHeight, emailStepHeight, "email", "summary");
    }
  });
}
