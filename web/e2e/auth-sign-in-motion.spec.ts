import { expect, test } from "@playwright/test";

for (const reducedMotion of ["no-preference", "reduce"] as const) {
  test(`sign-in steps keep their height and move focus with ${reducedMotion} motion`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion });
    await page.route("**/api/v1/me", route => route.fulfill({ status: 401, json: { detail: "unauthorized" } }));
    await page.goto("/login");
    const card = page.locator("[data-auth-entry-step]");
    const email = card.locator('input[type="email"]');
    const password = card.locator('input[autocomplete="current-password"]');
    await email.fill("demo@example.test");
    await page.evaluate(() => document.fonts.ready);
    const height = () => card.evaluate(el => el.getBoundingClientRect().height);
    const initialHeight = await height();
    expect(initialHeight).toBeGreaterThan(0);

    for (const [button, field] of [
      [card.locator('button[type="submit"]'), password],
      [card.getByRole("button", { name: "Editar" }), email],
    ] as const) {
      const motion = await button.evaluate(async (el: HTMLButtonElement) => {
        const card = el.closest<HTMLElement>("[data-auth-entry-step]")!;
        el.click();
        await Promise.resolve();
        const transitions = card.getAnimations({ subtree: true }).filter(
          (animation): animation is CSSTransition => animation instanceof CSSTransition &&
            animation.effect instanceof KeyframeEffect && animation.effect.target instanceof HTMLElement &&
            animation.effect.target.matches("[data-open]"),
        );
        for (const transition of transitions) {
          transition.pause();
          transition.currentTime = Number(transition.effect!.getTiming().duration) / 2;
        }
        // Let scheduled focus handlers run while both steps are still mid-transition.
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        const result = {
          height: card.getBoundingClientRect().height,
          visibleFields: [...card.querySelectorAll('input[type="email"], input[type="password"]')]
            .filter(field => field.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
            .map(field => field.getAttribute("autocomplete")),
          fades: transitions.filter(t => t.transitionProperty === "opacity").map(t => ({
            duration: Number(t.effect!.getTiming().duration),
            opacity: Number(getComputedStyle((t.effect as KeyframeEffect).target!).opacity),
          })),
          properties: transitions.map(t => t.transitionProperty),
          focusedInput: card.querySelector("input:focus")?.getAttribute("autocomplete"),
        };
        for (const transition of transitions) transition.play();
        return result;
      });
      await expect(field).toBeFocused();
      expect(await height()).toBe(initialHeight);
      expect(motion.height).toBe(initialHeight);
      const target = await field.getAttribute("autocomplete");
      if (reducedMotion === "reduce") {
        expect(motion.properties).toEqual([]);
        expect(motion.visibleFields).toEqual([target]);
        expect(motion.focusedInput).toBe(target);
      } else {
        expect(motion.visibleFields).toEqual(["email", "current-password"]);
        expect(motion.fades.length).toBeGreaterThanOrEqual(2);
        for (const fade of motion.fades) {
          expect(fade.duration).toBeGreaterThanOrEqual(200);
          expect(fade.duration).toBeLessThanOrEqual(250);
          expect(fade.opacity).toBeGreaterThan(0);
          expect(fade.opacity).toBeLessThan(1);
        }
        expect(motion.focusedInput).not.toBe(target);
      }
    }
  });
}

test("the end of a fade preserves a keyboard user's new focus", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("demo@example.test");
  const submit = page.locator('form button[type="submit"]');
  await submit.focus();
  await submit.evaluate(async (button: HTMLButtonElement) => {
    button.click();
    await Promise.resolve();
    for (const fade of button.form!.getAnimations({ subtree: true })) fade.pause();
  });
  await page.keyboard.press("Shift+Tab");
  const recovery = page.getByRole("link", { name: "¿Olvidaste tu contraseña?" });
  await expect(recovery).toBeFocused();
  await submit.evaluate(async (button: HTMLButtonElement) => {
    for (const fade of button.form!.getAnimations({ subtree: true })) fade.finish();
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
  });
  await expect(recovery).toBeFocused();
});
