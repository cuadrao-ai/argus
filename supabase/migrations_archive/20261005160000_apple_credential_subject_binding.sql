alter table public.apple_sign_in_credentials
    add column apple_subject text null
    check (apple_subject is null or (length(apple_subject) between 1 and 512 and apple_subject !~ '[[:space:][:cntrl:]]'));
