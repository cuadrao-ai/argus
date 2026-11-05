"use client";

import { useTranslation } from "react-i18next";

type ChatLegalNoticeProps = {
  showRegisteredDisclaimer?: boolean;
};

export default function ChatLegalNotice({
  showRegisteredDisclaimer = false,
}: ChatLegalNoticeProps) {
  const { t } = useTranslation();
  if (!showRegisteredDisclaimer) return null;

  return (
    <p
      data-testid="chat-disclaimer"
      className="mt-3 text-center text-[13px] font-normal leading-[1.45] text-black/40 dark:text-white/40"
    >
      {t(
        "chat.disclaimer",
        "Cuadrao can make mistakes. For education only. Not financial advice.",
      )}
    </p>
  );
}
