-- Take the index build's write-blocking lock before checking the existing rows.
-- A concurrent fiscal save cannot introduce a duplicate between the two steps.
do $$
begin
    lock table public.spaces in share mode;
    if exists (
        select 1
        from public.spaces
        where kind = 'business' and closed_at is null and business_rnc is not null
        group by argus_private.business_rnc_digits(business_rnc)
        having count(*) > 1
    ) then
        raise exception 'duplicate fiscal ID on open Businesses; index creation stopped'
            using errcode = '23505';
    end if;

    create unique index spaces_open_business_rnc_uidx
        on public.spaces (argus_private.business_rnc_digits(business_rnc))
        where kind = 'business' and closed_at is null and business_rnc is not null;

    grant execute on function argus_private.business_rnc_digits(text) to service_role;
end;
$$;
