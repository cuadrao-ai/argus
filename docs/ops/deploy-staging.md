# Deploy staging

Deploy one green commit to `cuadrao-api-staging`, `cuadrao-app-staging`, or both. The workflow is [Deploy staging](../../.github/workflows/deploy-staging.yml). `cuadrao-marketing-staging` stays out of this workflow.

1. Open Actions, choose Deploy staging, and run it from `codex/private-alpha-next`.
2. Leave the commit empty to deploy that ref. Or paste a full 40-character SHA that is already on `codex/private-alpha-next` and whose `ci` check succeeded.
3. Leave `force_all` off to deploy only the service whose paths changed. Turn `force_all` on to deploy both staging services.
4. Turn `dry_run` on to stop before the deploy request. The run still reads which commit is live.

Lucas adds the `RENDER_API_KEY` repository secret before the first run. The workflow reads that secret and does not turn auto-deploy on. A run with nothing deployable since the live commit skips and stays green. A newer dispatch waits for the running one. GitHub keeps only the newest pending run. The job waits until each requested deploy is live for that commit, and a failure stops the run.
