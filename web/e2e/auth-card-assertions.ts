import { expect, type Locator } from "@playwright/test";

type CardOwnership = {
  borderRadius: string;
  boxShadow: string;
  cardOwnerCount: number;
  hasBorder: boolean;
};

export async function expectOneCanonicalCard(
  surface: Locator,
): Promise<void> {
  const ownership = await surface.evaluate<CardOwnership>((element) => {
    const elements = [element, ...element.querySelectorAll<HTMLElement>("*")];
    const cardOwnerCount = elements.filter((candidate) => {
      const tag = candidate.tagName;
      if (tag === "INPUT" || tag === "BUTTON" || tag === "TEXTAREA" || tag === "SELECT") {
        return false;
      }
      const style = getComputedStyle(candidate);
      return (
        parseFloat(style.borderTopWidth) > 0 &&
        parseFloat(style.borderRadius) >= 12
      );
    }).length;
    const style = getComputedStyle(element);

    return {
      borderRadius: style.borderRadius,
      boxShadow: style.boxShadow,
      cardOwnerCount,
      hasBorder: parseFloat(style.borderTopWidth) > 0,
    };
  });

  expect(ownership).toEqual({
    borderRadius: "20px",
    boxShadow: "none",
    cardOwnerCount: 1,
    hasBorder: true,
  });
}
