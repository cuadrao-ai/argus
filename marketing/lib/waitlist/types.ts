export type WaitlistRow = {
  email_digest: string;
  email: string;
  created_at: string;
  confirmed_at: string | null;
  last_confirmation_sent_at: string | null;
  reminder_sent_at: string | null;
  privacy_policy_version: string;
  verification_id: string;
};

export type WaitlistStore = {
  register(input: { email: string; expenseMethod: string | null; wish: string | null }): Promise<WaitlistRow | null>;
  find(prefix: string, scope?: "active" | "deletion"): Promise<WaitlistRow | null>;
  confirm(id: string, issuedAt: string): Promise<WaitlistRow | null>;
  leave(id: string): Promise<void>;
  release(id: string, reservedAt: string, reminder: boolean): Promise<void>;
  reminders(): Promise<WaitlistRow[]>;
  purge(): Promise<number>;
};
