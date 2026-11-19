# Deploy staging

Deploy one green commit to the selected staging services in order: `cuadrao-api-staging`, `cuadrao-documents-worker-staging`, then `cuadrao-app-staging`. The workflow is [Deploy staging](../../.github/workflows/deploy-staging.yml). `cuadrao-marketing-staging` stays out of this workflow.

1. Open Actions, choose Deploy staging, and run it from `codex/private-alpha-next`.
2. Leave the commit empty to deploy that ref. Or paste a full 40-character SHA that is already on `codex/private-alpha-next` and whose `ci` check succeeded.
3. Leave `force_all` off to deploy only the service whose paths changed. Turn `force_all` on to deploy all three staging services.
4. Turn `dry_run` on to stop before the deploy request. The run still reads which commits are live and lists the selected services with the fixed target SHA.

Lucas adds the `RENDER_API_KEY` repository secret before the first run. The workflow reads that secret and does not turn auto-deploy on. A run with nothing deployable since the live commit skips and stays green. A newer dispatch waits for the running one. Only the newest pending run is kept. The job waits until each requested deploy is live for that commit, and a failure stops the run.

The worker deploys whenever the API deploys, and also when `workflows/` changes.
The API and worker compare against the older of their live commits, so changes
missing from either service still select a deploy. The workflow resolves one full
SHA at the start and uses it for every request and live-commit check. An API
failure stops the worker, and a worker failure stops the web deploy. The workflow
does not run migrations; approved migrations use `apply_approved_migrations.py`.
