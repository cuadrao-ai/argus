"use client";

import type { CSSProperties } from "react";
import { SavedIdentityMark } from "@/components/identity/IdentityMark";
import type { ApiUser } from "@/lib/argus-api";

export function profileInitial(profile: ApiUser | null) {
  const source =
    profile?.display_name?.trim() ||
    profile?.username?.trim() ||
    profile?.email?.trim() ||
    "A";
  return source.charAt(0).toUpperCase();
}

/** The person's 56px avatar: their saved mark, else the initial on their avatar color. */
export default function ProfileAvatar({ profile, className, style }: { profile: ApiUser | null; className: string; style: CSSProperties | undefined }) {
  return (
    <span aria-hidden="true" className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-[18px] font-bold ${className}`} style={style}>
      <SavedIdentityMark scope={profile?.id ? `person:${profile.id}` : ""} name={profile?.display_name ?? ""} size={56} fallback={profileInitial(profile)} />
    </span>
  );
}
