"use client";

import { useCallback, type Dispatch, type SetStateAction } from "react";

import { applyProfileUpdate, greetingNameFor } from "@/lib/account-profile";
import { dismissBusinessGuideCard, type BusinessGuideCardId } from "@/lib/business-guide-api";
import type { ApiUser, UserResponse } from "@/lib/guest-account";

/**
 * The shell's profile state: the greeting's name, and the callbacks that keep
 * the shell's copy current when a setting is saved or a guide is dismissed.
 */
export function useProfileUpdates(
  account: UserResponse | null,
  setAccount: Dispatch<SetStateAction<UserResponse | null>>,
): { onProfileUpdated: (user: ApiUser) => void; dismissGuideCard: (cardId: BusinessGuideCardId) => Promise<void>; greetingName: string | null } {
  const onProfileUpdated = useCallback(
    (user: ApiUser) => {
      setAccount((current) => applyProfileUpdate(current, user));
    },
    [setAccount],
  );
  const memberId = account?.user.id;
  // The guide leaves at once; a save the server refused puts it back for the same person.
  const dismissGuideCard = useCallback(async (cardId: BusinessGuideCardId) => {
    if (!memberId) return;
    const mark = (dismissed: boolean) => setAccount((current) => {
      const cards = current?.user.id === memberId ? current.dismissed_guide_cards : null;
      if (!current || !cards) return current;
      return { ...current, dismissed_guide_cards: dismissed ? [...cards, cardId] : cards.filter((id) => id !== cardId) };
    });
    mark(true);
    try {
      await dismissBusinessGuideCard({ cardId, expectedUserId: memberId });
    } catch (error) {
      mark(false);
      throw error;
    }
  }, [memberId, setAccount]);
  return { onProfileUpdated, dismissGuideCard, greetingName: greetingNameFor(account) };
}
