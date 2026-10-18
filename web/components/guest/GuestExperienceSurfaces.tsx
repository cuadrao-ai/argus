"use client";

import GuestConversionModal from "@/components/guest/GuestConversionModal";
import GuestNewConversationDialog from "@/components/guest/GuestNewConversationDialog";
import type { GuestExperience } from "@/components/guest/useGuestExperience";

export default function GuestExperienceSurfaces({
  experience,
}: {
  experience: GuestExperience;
}) {
  const { conversion, newConversation } = experience;
  return (
    <>
      {conversion.isOpen && (
        <GuestConversionModal
          isOpen
          reason={conversion.reason}
          initialMode={conversion.initialMode}
          resetAt={conversion.resetAt}
          resetKind={conversion.resetKind}
          locale={conversion.locale}
          publicAccountAccessEnabled={conversion.publicAccountAccessEnabled}
          onClose={conversion.close}
          onAuthenticate={conversion.authenticate}
          onEmailConfirmed={conversion.finishConfirmedSignup}
        />
      )}
      <GuestNewConversationDialog
        isOpen={newConversation.isOpen}
        isReplacing={newConversation.isReplacing}
        publicAccountAccessEnabled={conversion.publicAccountAccessEnabled}
        onCancel={newConversation.close}
        onStartOver={() => void newConversation.startOver()}
        onConvert={newConversation.convert}
      />
    </>
  );
}
