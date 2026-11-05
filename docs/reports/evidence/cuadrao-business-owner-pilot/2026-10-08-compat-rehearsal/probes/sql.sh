#!/bin/zsh
docker exec -i supabase_db_argus-biz-compat psql -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"
