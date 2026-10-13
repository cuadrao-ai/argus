"use client";

import { useState } from "react";
import ChatInterface from "@/components/chat/ChatInterface";
import ConversationShellGuard from "@/components/chat/ConversationShellGuard";
import ConversationUnavailableNotice from "./ConversationUnavailableNotice";
import { BusinessWorkspaceProvider } from "./BusinessWorkspace";
import { liveBusinessDataSource, type BusinessDataSource } from "./business-data";
import { createFixtureBusinessDataSource, type FixtureOptions } from "./fixture-data";

export default function BusinessApp({ sample }: { sample?: FixtureOptions }) {
  const [source] = useState<BusinessDataSource>(() =>
    sample ? createFixtureBusinessDataSource(sample) : liveBusinessDataSource,
  );
  return (
    <BusinessWorkspaceProvider source={source}>
      <ConversationShellGuard />
      <ConversationUnavailableNotice />
      <ChatInterface />
    </BusinessWorkspaceProvider>
  );
}
