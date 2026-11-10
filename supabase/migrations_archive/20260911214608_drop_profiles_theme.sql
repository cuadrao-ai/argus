-- Nothing reads or writes profiles.theme since #584; the theme lives in the
-- browser. The column's check constraint is dropped with it.
-- DROP is classified destructive by the promotion gate. The founder applies
-- this migration after a backup, before deploying the build that carries it.
-- Rolling back to a build from before #584 needs the column restored first.

alter table public.profiles drop column if exists theme;
