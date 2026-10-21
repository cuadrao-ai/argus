#!/bin/bash
# web.sh [on]: next dev on 3641 against the local API; the Business flag stays unset unless "on".
set -a; source "$(dirname "$0")/stack.env"; set +a
cd /Users/garces/Documents/projects/repos/argus-worktrees/business-pilot-spaces/web
unset NEXT_PUBLIC_BUSINESS_PILOT_ENABLED
[ "${1:-}" = on ] && export NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true
export NEXT_PUBLIC_SUPABASE_URL="$API_URL" NEXT_PUBLIC_SUPABASE_ANON_KEY="$ANON_KEY"
export NEXT_PUBLIC_ARGUS_API_URL=http://localhost:8641/api/v1 NEXT_PUBLIC_MOCK_AUTH=false NEXT_PUBLIC_ENABLE_SPANISH=true NEXT_TELEMETRY_DISABLED=1
unset API_URL ANON_KEY SERVICE_ROLE_KEY SECRET_KEY JWT_SECRET DB_URL PUBLISHABLE_KEY
exec node ./node_modules/next/dist/bin/next dev --port 3641
