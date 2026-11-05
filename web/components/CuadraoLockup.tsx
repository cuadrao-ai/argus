import Image from "next/image";

/**
 * The approved Cuadrao lockup as image files, never redrawn or set as text:
 * the light file on light, the dark file on dark (marketing/brand, see
 * .agent/designs/cuadrao/DESIGN.md "Brand identity"). The lockup files are
 * 268 by 56; `width` scales both.
 */
export function CuadraoLockup({ width, className = "" }: { width: number; className?: string }) {
  const height = Math.round((width * 56) / 268);
  return (
    <span className={`inline-block ${className}`} style={{ width }}>
      <Image unoptimized loading="eager" src="/brand/cuadrao-lockup-light.svg" alt="" width={width} height={height} className="h-auto w-full dark:hidden" />
      <Image unoptimized loading="eager" src="/brand/cuadrao-lockup-dark.svg" alt="" width={width} height={height} className="hidden h-auto w-full dark:block" />
    </span>
  );
}
