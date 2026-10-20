set lock_timeout = '5s';
set statement_timeout = '60s';

alter table public.spaces
    add column business_tax_id_type text;

update public.spaces
set business_tax_id_type = case char_length(business_rnc)
    when 9 then 'rnc'
    when 11 then 'cedula'
end
where business_rnc is not null
  and business_tax_id_type is null;

alter table public.spaces
    drop constraint business_rnc_shape,
    add constraint business_tax_id_pair check (
        (
            business_rnc is null
            and business_tax_id_type is null
        )
        or (
            kind = 'business'
            and business_rnc !~ '^0+$'
            and (
                (
                    business_tax_id_type = 'rnc'
                    and business_rnc ~ '^[0-9]{9}$'
                )
                or (
                    business_tax_id_type = 'cedula'
                    and business_rnc ~ '^[0-9]{11}$'
                )
            )
        )
    );

reset lock_timeout;
reset statement_timeout;
