-- Pending challenges keep the notice until the verified link takes ownership.
ALTER TABLE public.whatsapp_link_codes ADD COLUMN disclosure text;
