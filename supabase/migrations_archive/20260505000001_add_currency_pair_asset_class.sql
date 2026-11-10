alter table public.strategies
  drop constraint if exists strategies_asset_class_check;

alter table public.strategies
  add constraint strategies_asset_class_check
  check (asset_class in ('equity', 'crypto', 'currency_pair'));

alter table public.backtest_runs
  drop constraint if exists backtest_runs_asset_class_check;

alter table public.backtest_runs
  add constraint backtest_runs_asset_class_check
  check (asset_class in ('equity', 'crypto', 'currency_pair'));
