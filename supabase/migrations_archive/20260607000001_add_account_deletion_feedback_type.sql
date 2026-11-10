-- Allow private-alpha account deletion support requests through feedback.

alter table public.feedback
  drop constraint if exists feedback_type_check;

alter table public.feedback
  add constraint feedback_type_check
  check (type in ('bug', 'feature', 'general', 'account_deletion_request'));
