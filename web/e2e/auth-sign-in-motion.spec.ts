import { expect, test, type Locator } from "@playwright/test";
import { expectOneCanonicalCard } from "./auth-card-assertions";

type StepChange = { before: number; midway: number | null; afterOneFrame: number; transitions: string[] };

async function changeStep(button: Locator): Promise<StepChange> {
  return button.evaluate(async (el: HTMLButtonElement) => {
    const card = el.closest<HTMLElement>("[data-auth-entry-step]")!;
    const height = () => card.getBoundingClientRect().height;
    const before = height();
    el.click();
    await Promise.resolve();
    const transitions = card.getAnimations({ subtree: true }).filter(
      (animation): animation is CSSTransition => animation instanceof CSSTransition &&
        animation.effect instanceof KeyframeEffect && animation.effect.target instanceof HTMLElement &&
        animation.effect.target.matches("[data-open]"),
    );
    let midway: number | null = null;
    if (transitions.length > 0) {
      for (const transition of transitions) {
        transition.pause();
        transition.currentTime = Number(transition.effect!.getTiming().duration) / 2;
      }
      midway = height();
      for (const transition of transitions) transition.play();
    }
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    return { before, midway, afterOneFrame: height(), transitions: transitions.map(t => t.transitionProperty) };
  });
}

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
    }
  });
}
