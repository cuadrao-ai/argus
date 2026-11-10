-- Receipt reading is a second consent scope on the same row shape. The checks
-- become explicit allow-lists, so a future scope needs its own migration.
-- Safe on a live database: the old checks admit only scope 1, so every existing
-- row passes the new ones. One active consent per sender link stays: scope 2
-- replaces scope 1 and the reverse, never a second row.
alter table public.business_whatsapp_ai_consents
    drop constraint business_whatsapp_ai_consents_scope_version_check,
    drop constraint business_whatsapp_ai_consents_purpose_check,
    add constraint business_whatsapp_consent_scope_allowed
        check (scope_version in (1, 2)),
    add constraint business_whatsapp_consent_purpose_allowed
        check (purpose in (
            'business_whatsapp_draft_assistance',
            'business_whatsapp_receipt_reading'
        )),
    add constraint business_whatsapp_consent_scope_purpose_pair check (
        (scope_version = 1 and purpose = 'business_whatsapp_draft_assistance')
        or (scope_version = 2 and purpose = 'business_whatsapp_receipt_reading')
    );
