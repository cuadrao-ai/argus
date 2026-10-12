import Image from "next/image";

/**
 * The approved Cuadrao mark as image files, never redrawn: the light mark on
 * light and the dark mark on dark (marketing/brand, see
 * .agent/designs/cuadrao/DESIGN.md "Brand identity").
 */
export function CuadraoMark({
  size,
  className = "",
  testId,
}: {
  size: number;
  className?: string;
  testId?: string;
}) {
  return (
    <>
      <Image
        unoptimized
        loading="eager"
        src="/brand/cuadrao-mark-light.svg"
        width={size}
        height={size}
        alt=""
        aria-hidden="true"
        className={`${className} dark:hidden`}
        data-testid={testId}
      />
      <Image
        unoptimized
        loading="eager"
        src="/brand/cuadrao-mark-dark.svg"
        width={size}
        height={size}
        alt=""
        aria-hidden="true"
        className={`${className} hidden dark:block`}
      />
    </>
  );
}
