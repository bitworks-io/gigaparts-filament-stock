# GigaParts Stock Alerts Worker

Cloudflare Worker backend for saved filament restock notifications.

## Required Cloudflare Resources

- Worker: `gigaparts-stock-alerts`
- D1 database: `gigaparts-stock-alerts-db`
- Worker secrets:
  - `VAPID_PRIVATE_KEY`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_WEBHOOK_SECRET`
  - `STOCK_EVENT_TOKEN`
- Worker vars:
  - `VAPID_PUBLIC_KEY`
  - `VAPID_SUBJECT`
  - `TELEGRAM_BOT_USERNAME`
  - `ALLOWED_ORIGINS`

## Deploy

```sh
npm install
npx wrangler login
npx wrangler d1 create gigaparts-stock-alerts-db
npx wrangler d1 migrations apply gigaparts-stock-alerts-db --local
npx wrangler d1 migrations apply gigaparts-stock-alerts-db --remote
npx wrangler secret put VAPID_PRIVATE_KEY
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
npx wrangler secret put STOCK_EVENT_TOKEN
npx wrangler deploy
```

After deploy, configure Telegram with the deployed Worker URL:

```sh
curl -sS "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "content-type: application/json" \
  -d '{"url":"https://<worker-url>/telegram/webhook","secret_token":"'"$TELEGRAM_WEBHOOK_SECRET"'"}'
```

GitHub Actions needs:

- `NOTIFY_WORKER_URL=https://<worker-url>/api/stock-events`
- `NOTIFY_WORKER_TOKEN=<same value as STOCK_EVENT_TOKEN>`

## Telegram Bot Commands

After a user opens the pairing link from the tracker, the bot confirms the
connection and summarizes the available commands:

- `/list` - show the Telegram-synced saved filament list for that chat.
- `/status` - show whether the chat is connected and how many saved items are
  synced.
- `/help` - show a short usage summary and tracker link.

Saved-list replies are capped before Telegram delivery so a large saved list
cannot produce an oversized bot response.
