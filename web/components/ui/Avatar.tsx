"use client";

import { useState } from "react";
import { User } from "lucide-react";

export type AvatarSize = 24 | 32 | 40;
export type AvatarStatus = "pending" | null;

/**
 * Tints that keep their initials at 4.5:1 or better. A name always maps to
 * the same tint, so a person keeps one color everywhere they appear.
 */
const TINTS = [
  { bg: "#e3ebe1", fg: "#2f5a49" },
  { bg: "#f2e8c9", fg: "#5c4910" },
  { bg: "#dde7ef", fg: "#2c5170" },
  { bg: "#f1e0ea", fg: "#7a2f57" },
  { bg: "#e7e2f3", fg: "#4a3d78" },
  { bg: "#e0eeeb", fg: "#1f5c55" },
  { bg: "#f3e2d9", fg: "#7a3d1c" },
  { bg: "#e8e8e3", fg: "#3d4a45" },
] as const;

function tintFor(seed: string) {
  let hash = 0;
  for (const char of seed.toLocaleLowerCase()) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return TINTS[hash % TINTS.length];
}

/** Two initials from a name; an email uses its part before the @. */
export function initialsOf(name: string | null | undefined): string {
  const source = (name ?? "").split("@")[0].replace(/[._-]+/g, " ").trim();
  if (!source) return "";
  const words = source.split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words[words.length - 1]].map((word) => [...word][0]) : [...words[0]].slice(0, 2);
  return letters.join("").toLocaleUpperCase();
}

const SIZE: Record<AvatarSize, string> = { 24: "h-6 w-6 text-[10px]", 32: "h-8 w-8 text-[12px]", 40: "h-10 w-10 text-[14px]" };
const ICON: Record<AvatarSize, string> = { 24: "h-3.5 w-3.5", 32: "h-4 w-4", 40: "h-5 w-5" };

/**
 * The one avatar: the person's photo when there is one, else two initials on
 * a tint chosen by their name, else a person icon. `pending` (an invite not yet
 * accepted) draws a dashed ring instead of a fill, so status is never color alone.
 * Always round, so it never reads as the business's square mark.
 */
export function Avatar({ name, src, size = 32, status = null, className = "", testId }: {
  name?: string | null;
  src?: string | null;
  size?: AvatarSize;
  status?: AvatarStatus;
  className?: string;
  testId?: string;
}) {
  const [broken, setBroken] = useState(false);
  const initials = initialsOf(name);
  const tint = tintFor(name ?? "");
  const pending = status === "pending";
  const base = `relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-medium leading-none ${SIZE[size]} ${className}`;
  if (src && !broken) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" aria-hidden="true" data-testid={testId} onError={() => setBroken(true)} className={`${base} object-cover`} />;
  }
  return (
    <span
      aria-hidden="true"
      data-testid={testId}
      data-avatar={initials ? "initials" : "icon"}
      style={pending ? { color: tint.fg } : { backgroundColor: tint.bg, color: tint.fg }}
      className={`${base} ${pending ? "border border-dashed border-current bg-transparent" : ""}`}
    >
      {initials || <User className={ICON[size]} strokeWidth={2} />}
    </span>
  );
}

/** Overlapping avatars for a group; past `max` the rest show as "+N". */
export function AvatarGroup({ people, max = 3, size = 24, label }: { people: readonly { name: string | null; src?: string | null }[]; max?: number; size?: AvatarSize; label: string }) {
  const shown = people.slice(0, max);
  const rest = people.length - shown.length;
  return (
    <span role="img" aria-label={label} className="inline-flex items-center">
      {shown.map((person, index) => (
        <Avatar key={`${person.name}-${index}`} name={person.name} src={person.src} size={size} className={`ring-2 ring-[#FFFEFA] dark:ring-[#1f2225] ${index ? "-ml-1.5" : ""}`} />
      ))}
      {rest > 0 ? <span className={`-ml-1.5 inline-flex items-center justify-center rounded-full bg-[#EDECE6] font-medium tabular-nums text-[#3d4a45] ring-2 ring-[#FFFEFA] dark:bg-white/10 dark:text-white/80 dark:ring-[#1f2225] ${SIZE[size]}`}>+{rest}</span> : null}
    </span>
  );
}
