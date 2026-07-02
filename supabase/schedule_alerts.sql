-- Supabase cron for Google News FR alerts.
-- À lancer après avoir déployé la Edge Function `process-alerts`.
--
-- Avant de lancer ce fichier, remplacez les trois valeurs ci-dessous:
--   YOUR_SUPABASE_ANON_KEY: clé anon/public du projet
--   CHANGE_ME_LONG_RANDOM_SECRET: secret long au hasard, aussi à mettre dans ALERT_CRON_SECRET

create extension if not exists pg_cron with schema extensions;
create extension if not exists pg_net with schema extensions;
create extension if not exists supabase_vault with schema vault;

select vault.create_secret('https://sopvxssamctizjbbtsrl.supabase.co', 'google_news_project_url');
select vault.create_secret('YOUR_SUPABASE_ANON_KEY', 'google_news_publishable_key');
select vault.create_secret('CHANGE_ME_LONG_RANDOM_SECRET', 'google_news_alert_cron_secret');

do $$
begin
  perform cron.unschedule('google-news-process-alerts-every-5-minutes');
  perform cron.unschedule('google-news-process-alerts-every-minute');
exception when others then
  null;
end $$;

select cron.schedule(
  'google-news-process-alerts-every-minute',
  '* * * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'google_news_project_url' order by created_at desc limit 1) || '/functions/v1/process-alerts',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'apikey', (select decrypted_secret from vault.decrypted_secrets where name = 'google_news_publishable_key' order by created_at desc limit 1),
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'google_news_publishable_key' order by created_at desc limit 1),
      'x-alert-cron-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'google_news_alert_cron_secret' order by created_at desc limit 1)
    ),
    body := jsonb_build_object('action', 'all')
  ) as request_id;
  $$
);
