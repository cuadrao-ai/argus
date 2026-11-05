import supportContact from "../argus_display_contract/support_contact.json";

// Release builds pin NEXT_PUBLIC_CUADRAO_SUPPORT_EMAIL, or the older
// NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL; the Cuadrao name wins when both are set.
// Unset or blank uses the address the API reads from the same contract file.
// This file is the only reader of either name (tests/test_support_email_agreement.py).
const configured =
  (process.env.NEXT_PUBLIC_CUADRAO_SUPPORT_EMAIL ?? "").trim() ||
  (process.env.NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL ?? "");

export const supportEmail = configured.trim() || supportContact.email;
