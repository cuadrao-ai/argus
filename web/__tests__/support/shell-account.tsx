import { useMemo, useState, type ReactNode } from "react";
import { PanelShellProvider, type ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useProfileUpdates } from "@/components/chat/useProfileUpdates";
import type { UserResponse } from "@/lib/guest-account";

const NO_SHELL: Partial<ChatShellBridge> = {};
type Account = { member: string | null; dismissed: string[] | null };
const accountFor = ({ member, dismissed }: Account) => member ? { user: { id: member }, dismissed_guide_cards: dismissed } as unknown as UserResponse : null;

/** The shell's account as a panel sees it, kept by the shell's own hook. A new `member` replaces the account the way a new /me answer does; `member: null` is an account that never answered. */
export function useShellAccount(start: Account, base: Partial<ChatShellBridge> = NO_SHELL): ChatShellBridge {
  const [account, setAccount] = useState(() => accountFor(start));
  const [member, setMember] = useState(start.member);
  if (member !== start.member) {
    setMember(start.member);
    setAccount(accountFor(start));
  }
  const { dismissGuideCard } = useProfileUpdates(account, setAccount);
  return useMemo(() => ({ ...base, memberId: account?.user.id ?? null, dismissedGuideCards: account?.dismissed_guide_cards, dismissGuideCard }) as ChatShellBridge, [base, account, dismissGuideCard]);
}

export function ShellAccount({ children, ...start }: Account & { children: ReactNode }) {
  return <PanelShellProvider value={useShellAccount(start)}>{children}</PanelShellProvider>;
}
