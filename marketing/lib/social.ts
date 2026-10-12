export type SocialPlatform = {
  id: "tiktok" | "instagram" | "youtube";
  label: string;
  /** Set when the account exists. A platform without one only shows in preview. */
  href: string | null;
};

export const SOCIAL_PLATFORMS: readonly SocialPlatform[] = [
  { id: "tiktok", label: "TikTok", href: null },
  { id: "instagram", label: "Instagram", href: null },
  { id: "youtube", label: "YouTube", href: null },
];

export function socialPreviewEnabled(value: string | undefined): boolean {
  return value === "1";
}

export function visibleSocials(
  platforms: readonly SocialPlatform[],
  preview: boolean,
): SocialPlatform[] {
  return platforms.filter((platform) => platform.href !== null || preview);
}
