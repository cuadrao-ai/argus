import { CuadraoLockup } from "@/components/CuadraoLockup";
import GuestEmptyStateIntro from "@/components/guest/GuestEmptyStateIntro";

export default function EmptyChatHeading({ isGuest }: { isGuest: boolean }) {
  return (
    <>
      <h1 aria-label="Cuadrao" className={`flex justify-center ${isGuest ? "mb-3" : "mb-8"}`}>
        <CuadraoLockup width={200} />
      </h1>
      {isGuest ? <GuestEmptyStateIntro /> : null}
    </>
  );
}
