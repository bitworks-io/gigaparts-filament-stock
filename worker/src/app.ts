import { ApplicationServerKeys, generatePushHTTPRequest } from "webpush-webcrypto";

export interface Env {
  DB?: D1Database;
  ALLOWED_ORIGINS: string;
  VAPID_PUBLIC_KEY: string;
  VAPID_PRIVATE_KEY: string;
  VAPID_SUBJECT: string;
  TELEGRAM_BOT_USERNAME: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_WEBHOOK_SECRET: string;
  STOCK_EVENT_TOKEN: string;
}

export interface WebPushSubscriptionRecord {
  endpoint: string;
  p256dh: string;
  auth: string;
}

export interface TelegramLink {
  chatId: string;
  username?: string;
}

export interface DeviceRecord {
  id: string;
  tokenHash: string;
}

export interface StockItem {
  key: string;
  brand?: string;
  line?: string;
  name?: string;
  sku?: string;
  url?: string;
}

export interface StockEventPayload {
  updatedAt: string;
  changes: {
    inStock: StockItem[];
  };
}

export interface NotificationPayload {
  title: string;
  body: string;
  url: string;
}

export interface Store {
  createDevice(rawToken: string): Promise<DeviceRecord>;
  touchDevice(deviceId: string): Promise<void>;
  getDevice(deviceId: string): Promise<DeviceRecord | null>;
  replaceSavedItems(deviceId: string, itemKeys: string[]): Promise<void>;
  savedItems(deviceId: string): Promise<string[]>;
  upsertWebPushSubscription(deviceId: string, subscription: WebPushSubscriptionRecord): Promise<void>;
  removeWebPushSubscriptions(deviceId: string): Promise<void>;
  webPushSubscriptions(deviceId: string): Promise<WebPushSubscriptionRecord[]>;
  createTelegramPairingToken(rawToken: string, deviceId: string, expiresAt: string): Promise<void>;
  consumeTelegramPairingToken(rawToken: string, now: string): Promise<string | null>;
  upsertTelegramLink(deviceId: string, link: TelegramLink): Promise<void>;
  removeTelegramLink(deviceId: string): Promise<void>;
  telegramLink(deviceId: string): Promise<TelegramLink | null>;
  telegramSavedItems(chatId: string): Promise<string[]>;
  telegramLinkedDeviceCount(chatId: string): Promise<number>;
  replaceTelegramSavedItems(chatId: string, itemKeys: string[]): Promise<void>;
  mergeTelegramSavedItems(chatId: string, itemKeys: string[]): Promise<void>;
  telegramChatsWithSavedItem(itemKey: string): Promise<string[]>;
  devicesWithSavedItem(itemKey: string): Promise<string[]>;
  hasNotification(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string): Promise<boolean>;
  recordNotification(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string, status: string, error?: string): Promise<void>;
  incrementRateLimit(key: string, windowStart: string): Promise<number>;
}

type Fetcher = typeof fetch;
type WebPushDeliverer = (subscription: WebPushSubscriptionRecord, payload: NotificationPayload, env: Env) => Promise<void>;
type TelegramDeliverer = (chatId: string, payload: NotificationPayload, env: Env) => Promise<void>;

interface AppOptions {
  store?: Store;
  fetcher?: Fetcher;
  deliverWebPush?: WebPushDeliverer;
  deliverTelegram?: TelegramDeliverer;
  now?: () => Date;
  randomToken?: () => string;
}

const MAX_SAVED_ITEMS = 500;
const MAX_REQUEST_BYTES = 64 * 1024;
const PAIRING_TTL_MS = 15 * 60 * 1000;

export function createApp(options: AppOptions = {}) {
  return {
    async fetch(request: Request, env: Env): Promise<Response> {
      const origin = request.headers.get("origin") || "";
      const corsHeaders = cors(env, origin);
      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: corsHeaders });
      }

      try {
        const url = new URL(request.url);
        const store = options.store || (env.DB ? new D1Store(env.DB) : null);
        const now = options.now || (() => new Date());
        const randomToken = options.randomToken || generateToken;
        const fetcher = options.fetcher || fetch;
        const deliverWebPush = options.deliverWebPush || defaultDeliverWebPush;
        const deliverTelegram = options.deliverTelegram || ((chatId, payload, appEnv) => defaultDeliverTelegram(chatId, payload, appEnv, fetcher));

        if (url.pathname === "/api/config" && request.method === "GET") {
          return jsonResponse({
            vapidPublicKey: env.VAPID_PUBLIC_KEY,
            telegramBotUsername: env.TELEGRAM_BOT_USERNAME
          }, 200, corsHeaders);
        }

        if (!store) {
          return jsonResponse({ error: "Storage is not configured" }, 500, corsHeaders);
        }

        if (url.pathname === "/api/devices" && request.method === "POST") {
          if (!await withinRateLimit(request, store, "devices:create", 30, 60 * 60, now())) {
            return jsonResponse({ error: "Rate limit exceeded" }, 429, corsHeaders);
          }
          const deviceToken = randomToken();
          const device = await store.createDevice(deviceToken);
          return jsonResponse({ deviceId: device.id, deviceToken }, 201, corsHeaders);
        }

        const savedMatch = url.pathname.match(/^\/api\/devices\/([^/]+)\/saved-items$/);
        if (savedMatch && request.method === "PUT") {
          const device = await authenticateDevice(request, store, savedMatch[1]);
          if (!device) return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          const body = await parseJson(request);
          const itemKeys = normalizeItemKeys(body?.itemKeys);
          await store.replaceSavedItems(device.id, itemKeys);
          const telegram = await store.telegramLink(device.id);
          if (telegram) await store.replaceTelegramSavedItems(telegram.chatId, itemKeys);
          await store.touchDevice(device.id);
          return new Response(null, { status: 204, headers: corsHeaders });
        }

        const pushMatch = url.pathname.match(/^\/api\/devices\/([^/]+)\/web-push-subscription$/);
        if (pushMatch && request.method === "POST") {
          const device = await authenticateDevice(request, store, pushMatch[1]);
          if (!device) return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          const body = await parseJson(request);
          const subscription = normalizePushSubscription(body?.subscription);
          if (!subscription) return jsonResponse({ error: "Invalid subscription" }, 400, corsHeaders);
          await store.upsertWebPushSubscription(device.id, subscription);
          await store.touchDevice(device.id);
          return new Response(null, { status: 204, headers: corsHeaders });
        }

        if (pushMatch && request.method === "DELETE") {
          const device = await authenticateDevice(request, store, pushMatch[1]);
          if (!device) return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          await store.removeWebPushSubscriptions(device.id);
          await store.touchDevice(device.id);
          return new Response(null, { status: 204, headers: corsHeaders });
        }

        const telegramMatch = url.pathname.match(/^\/api\/devices\/([^/]+)\/telegram-link$/);
        if (telegramMatch && request.method === "GET") {
          const device = await authenticateDevice(request, store, telegramMatch[1]);
          if (!device) return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          const telegram = await store.telegramLink(device.id);
          return jsonResponse({
            linked: Boolean(telegram),
            username: telegram?.username || "",
            itemKeys: telegram ? await store.telegramSavedItems(telegram.chatId) : []
          }, 200, corsHeaders);
        }

        if (telegramMatch && request.method === "POST") {
          const device = await authenticateDevice(request, store, telegramMatch[1]);
          if (!device) return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          if (!env.TELEGRAM_BOT_USERNAME) return jsonResponse({ error: "Telegram is not configured" }, 503, corsHeaders);
          if (!await withinRateLimit(request, store, `telegram:pair:${device.id}`, 20, 60 * 60, now())) {
            return jsonResponse({ error: "Rate limit exceeded" }, 429, corsHeaders);
          }
          const pairingToken = randomToken();
          const expiresAt = new Date(now().getTime() + PAIRING_TTL_MS).toISOString();
          await store.createTelegramPairingToken(pairingToken, device.id, expiresAt);
          await store.touchDevice(device.id);
          return jsonResponse({
            pairingToken,
            pairingUrl: `https://t.me/${env.TELEGRAM_BOT_USERNAME}?start=${pairingToken}`,
            expiresAt
          }, 200, corsHeaders);
        }

        if (telegramMatch && request.method === "DELETE") {
          const device = await authenticateDevice(request, store, telegramMatch[1]);
          if (!device) return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          await store.removeTelegramLink(device.id);
          await store.touchDevice(device.id);
          return new Response(null, { status: 204, headers: corsHeaders });
        }

        if (url.pathname === "/telegram/webhook" && request.method === "POST") {
          if (request.headers.get("x-telegram-bot-api-secret-token") !== env.TELEGRAM_WEBHOOK_SECRET) {
            return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          }
          const update = await parseJson(request);
          await handleTelegramUpdate(update, store, env, fetcher, now());
          return new Response(null, { status: 204, headers: corsHeaders });
        }

        if (url.pathname === "/api/stock-events" && request.method === "POST") {
          if (bearerToken(request) !== env.STOCK_EVENT_TOKEN) {
            return jsonResponse({ error: "Unauthorized" }, 401, corsHeaders);
          }
          const payload = normalizeStockEventPayload(await parseJson(request));
          if (!payload) return jsonResponse({ error: "Invalid stock event" }, 400, corsHeaders);
          const result = await handleStockEvent(payload, store, env, deliverWebPush, deliverTelegram);
          return jsonResponse(result, 202, corsHeaders);
        }

        return jsonResponse({ error: "Not found" }, 404, corsHeaders);
      } catch (error) {
        if (error instanceof HttpError) {
          return jsonResponse({ error: error.message }, error.status, corsHeaders);
        }
        return jsonResponse({ error: error instanceof Error ? error.message : "Internal error" }, 500, corsHeaders);
      }
    }
  };
}

async function authenticateDevice(request: Request, store: Store, deviceId: string): Promise<DeviceRecord | null> {
  const token = bearerToken(request);
  if (!token) return null;
  const device = await store.getDevice(deviceId);
  if (!device) return null;
  return device.tokenHash === await hashToken(token) ? device : null;
}

function bearerToken(request: Request): string {
  const auth = request.headers.get("authorization") || "";
  return auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
}

class HttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

async function parseJson(request: Request): Promise<any> {
  const contentLength = Number(request.headers.get("content-length") || "0");
  if (contentLength > MAX_REQUEST_BYTES) throw new HttpError(413, "Request body is too large");
  try {
    const body = await request.text();
    if (body.length > MAX_REQUEST_BYTES) throw new HttpError(413, "Request body is too large");
    return body ? JSON.parse(body) : null;
  } catch (error) {
    if (error instanceof HttpError) throw error;
    return null;
  }
}

function normalizeItemKeys(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string") continue;
    const trimmed = item.trim();
    if (!trimmed || trimmed.length > 500) continue;
    seen.add(trimmed);
    if (seen.size >= MAX_SAVED_ITEMS) break;
  }
  return [...seen];
}

function normalizePushSubscription(value: unknown): WebPushSubscriptionRecord | null {
  const sub = value as { endpoint?: unknown; keys?: { p256dh?: unknown; auth?: unknown } };
  if (!sub || typeof sub.endpoint !== "string" || !sub.endpoint.startsWith("https://")) return null;
  if (!sub.keys || typeof sub.keys.p256dh !== "string" || typeof sub.keys.auth !== "string") return null;
  return { endpoint: sub.endpoint, p256dh: sub.keys.p256dh, auth: sub.keys.auth };
}

function normalizeStockEventPayload(value: unknown): StockEventPayload | null {
  const payload = value as StockEventPayload;
  if (!payload || typeof payload.updatedAt !== "string" || !payload.changes || !Array.isArray(payload.changes.inStock)) {
    return null;
  }
  return {
    updatedAt: payload.updatedAt,
    changes: {
      inStock: payload.changes.inStock
        .filter(item => item && typeof item.key === "string")
        .slice(0, 500)
        .map(item => ({
          key: item.key,
          brand: text(item.brand),
          line: text(item.line),
          name: text(item.name),
          sku: text(item.sku),
          url: safeUrl(item.url)
        }))
    }
  };
}

function text(value: unknown): string {
  return typeof value === "string" ? value.slice(0, 1000) : "";
}

function safeUrl(value: unknown): string {
  if (typeof value !== "string" || value.length > 2000) return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
}

async function withinRateLimit(request: Request, store: Store, scope: string, limit: number, windowSeconds: number, now: Date): Promise<boolean> {
  const ip = request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for") || "unknown";
  const ipHash = await hashToken(ip.split(",")[0].trim());
  const windowStartMs = Math.floor(now.getTime() / (windowSeconds * 1000)) * windowSeconds * 1000;
  const key = `${scope}:${ipHash}`;
  const count = await store.incrementRateLimit(key, new Date(windowStartMs).toISOString());
  return count <= limit;
}

async function handleTelegramUpdate(update: any, store: Store, env: Env, fetcher: Fetcher, now: Date): Promise<void> {
  const message = update?.message;
  const textValue = typeof message?.text === "string" ? message.text : "";
  const chatId = message?.chat?.id == null ? "" : String(message.chat.id);
  if (!chatId || !textValue) return;
  if (!await withinTelegramRateLimit(store, chatId, now)) return;

  const command = parseTelegramCommand(textValue, env.TELEGRAM_BOT_USERNAME);
  if (!command) {
    await sendTelegramMessage(fetcher, env, chatId, unknownTelegramCommandMessage());
    return;
  }

  if (command.name === "start") {
    if (command.argument) {
      const deviceId = await store.consumeTelegramPairingToken(command.argument, now.toISOString());
      if (!deviceId) {
        await sendTelegramMessage(fetcher, env, chatId, "This GigaParts stock alert link is expired or already used. Open the tracker and connect Telegram again.");
        return;
      }

      const username = typeof message.chat.username === "string" ? message.chat.username : undefined;
      await store.upsertTelegramLink(deviceId, { chatId, username });
      await store.mergeTelegramSavedItems(chatId, await store.savedItems(deviceId));
      const itemCount = (await store.telegramSavedItems(chatId)).length;
      await sendTelegramMessage(fetcher, env, chatId, telegramConnectedMessage(itemCount));
      return;
    }

    await sendTelegramMessage(fetcher, env, chatId, await telegramStatusMessage(store, chatId));
    return;
  }

  if (command.name === "list") {
    await sendTelegramMessage(fetcher, env, chatId, await telegramSavedListMessage(store, chatId));
    return;
  }

  if (command.name === "status") {
    await sendTelegramMessage(fetcher, env, chatId, await telegramStatusMessage(store, chatId));
    return;
  }

  if (command.name === "help") {
    await sendTelegramMessage(fetcher, env, chatId, telegramHelpMessage());
    return;
  }

  await sendTelegramMessage(fetcher, env, chatId, unknownTelegramCommandMessage());
}

function parseTelegramCommand(textValue: string, botUsername: string): { name: string; argument: string } | null {
  const trimmed = textValue.trim();
  const match = trimmed.match(/^\/([A-Za-z0-9_]+)(?:@([A-Za-z0-9_]+))?(?:\s+(.+))?$/);
  if (!match) return null;
  const targetBot = match[2] || "";
  if (targetBot && botUsername && targetBot.toLowerCase() !== botUsername.toLowerCase()) return null;
  return {
    name: match[1].toLowerCase(),
    argument: (match[3] || "").trim()
  };
}

async function withinTelegramRateLimit(store: Store, chatId: string, now: Date): Promise<boolean> {
  const windowSeconds = 60 * 60;
  const windowStartMs = Math.floor(now.getTime() / (windowSeconds * 1000)) * windowSeconds * 1000;
  const chatHash = await hashToken(chatId);
  const count = await store.incrementRateLimit(`telegram:chat:${chatHash}`, new Date(windowStartMs).toISOString());
  return count <= 60;
}

function telegramConnectedMessage(itemCount: number): string {
  return [
    "Telegram is connected. Saved filament restock alerts will be sent here.",
    "",
    `Current saved list: ${itemCount} saved ${itemCount === 1 ? "item" : "items"}.`,
    "Commands:",
    "/list - show your Telegram-synced saved list",
    "/status - show connection status",
    "/help - show bot help"
  ].join("\n");
}

function telegramHelpMessage(): string {
  return [
    "GigaParts Filament Stock Alerts",
    "",
    "This bot sends restock alerts for filament saved on the tracker after Telegram is connected.",
    "",
    "Commands:",
    "/list - show your Telegram-synced saved list",
    "/status - show connection status and saved count",
    "/help - show this help",
    "",
    "Tracker: https://bitworks-io.github.io/gigaparts-filament-stock/"
  ].join("\n");
}

async function telegramStatusMessage(store: Store, chatId: string): Promise<string> {
  const linkedDevices = await store.telegramLinkedDeviceCount(chatId);
  if (!linkedDevices) {
    return [
      "This Telegram chat is not connected yet.",
      "Open the tracker, choose Connect Telegram, then open the pairing link here.",
      "",
      "Tracker: https://bitworks-io.github.io/gigaparts-filament-stock/"
    ].join("\n");
  }

  const savedCount = (await store.telegramSavedItems(chatId)).length;
  return [
    `Connected. ${savedCount} saved ${savedCount === 1 ? "item" : "items"} are synced to this Telegram chat.`,
    "Use /list to show the saved list or /help for commands."
  ].join("\n");
}

async function telegramSavedListMessage(store: Store, chatId: string): Promise<string> {
  if (!await store.telegramLinkedDeviceCount(chatId)) {
    return [
      "This Telegram chat is not connected yet.",
      "Open the tracker, choose Connect Telegram, then open the pairing link here."
    ].join("\n");
  }

  const items = await store.telegramSavedItems(chatId);
  if (!items.length) {
    return [
      "Your Telegram-synced saved filament list is empty.",
      "Add filaments on the tracker and they will sync here after Telegram is connected."
    ].join("\n");
  }

  const lines = [`Saved filament list (${items.length} ${items.length === 1 ? "item" : "items"}):`];
  let shown = 0;
  for (const itemKey of items) {
    const row = `${shown + 1}. ${formatSavedItemKey(itemKey)}`;
    if (shown >= 50 || lines.join("\n").length + row.length + 80 > 3500) break;
    lines.push(row);
    shown += 1;
  }
  if (shown < items.length) lines.push(`...and ${items.length - shown} more. Open the tracker for the full list.`);
  lines.push("", "Tracker: https://bitworks-io.github.io/gigaparts-filament-stock/");
  return lines.join("\n");
}

function formatSavedItemKey(itemKey: string): string {
  const parts = itemKey.split("|").map(part => part.trim()).filter(Boolean);
  return (parts.length ? parts.join(" - ") : itemKey).slice(0, 160);
}

function unknownTelegramCommandMessage(): string {
  return "I do not understand that command. Send /help for available GigaParts stock alert commands.";
}

async function handleStockEvent(
  payload: StockEventPayload,
  store: Store,
  env: Env,
  deliverWebPush: WebPushDeliverer,
  deliverTelegram: TelegramDeliverer
): Promise<{ matchedItems: number; attempted: number; sent: number; skipped: number }> {
  let matchedItems = 0;
  let attempted = 0;
  let sent = 0;
  let skipped = 0;
  const telegramTargetsSeen = new Set<string>();

  for (const item of payload.changes.inStock) {
    const deviceIds = await store.devicesWithSavedItem(item.key);
    const telegramChatIds = await store.telegramChatsWithSavedItem(item.key);
    if (deviceIds.length || telegramChatIds.length) matchedItems += 1;
    for (const deviceId of deviceIds) {
      const notification = notificationPayload(item);
      for (const subscription of await store.webPushSubscriptions(deviceId)) {
        const targetHash = await hashToken(subscription.endpoint);
        if (await store.hasNotification(payload.updatedAt, item.key, "web-push", targetHash)) {
          skipped += 1;
          continue;
        }
        attempted += 1;
        try {
          await deliverWebPush(subscription, notification, env);
          await store.recordNotification(payload.updatedAt, item.key, "web-push", targetHash, "sent");
          sent += 1;
        } catch (error) {
          await store.recordNotification(payload.updatedAt, item.key, "web-push", targetHash, "failed", errorMessage(error));
        }
      }
    }

    const notification = notificationPayload(item);
    for (const chatId of telegramChatIds) {
      const targetKey = `${item.key}|${chatId}`;
      const targetHash = await hashToken(chatId);
      if (telegramTargetsSeen.has(targetKey) || await store.hasNotification(payload.updatedAt, item.key, "telegram", targetHash)) {
        skipped += 1;
        continue;
      }
      telegramTargetsSeen.add(targetKey);
      attempted += 1;
      try {
        await deliverTelegram(chatId, notification, env);
        await store.recordNotification(payload.updatedAt, item.key, "telegram", targetHash, "sent");
        sent += 1;
      } catch (error) {
        await store.recordNotification(payload.updatedAt, item.key, "telegram", targetHash, "failed", errorMessage(error));
      }
    }
  }
  return { matchedItems, attempted, sent, skipped };
}

function notificationPayload(item: StockItem): NotificationPayload {
  const titleParts = [item.brand, item.line].filter(Boolean);
  const title = `${titleParts.join(" - ") || "GigaParts filament"} in stock`;
  const sku = item.sku ? ` (${item.sku})` : "";
  return {
    title,
    body: `${item.name || "Saved filament"}${sku}`,
    url: item.url || "https://bitworks-io.github.io/gigaparts-filament-stock/"
  };
}

async function defaultDeliverWebPush(subscription: WebPushSubscriptionRecord, payload: NotificationPayload, env: Env): Promise<void> {
  const applicationServerKeys = await ApplicationServerKeys.fromJSON({
    publicKey: env.VAPID_PUBLIC_KEY,
    privateKey: env.VAPID_PRIVATE_KEY
  });
  const request = await generatePushHTTPRequest({
    applicationServerKeys,
    payload: JSON.stringify(payload),
    target: {
      endpoint: subscription.endpoint,
      keys: {
        p256dh: subscription.p256dh,
        auth: subscription.auth
      }
    },
    adminContact: env.VAPID_SUBJECT,
    ttl: 60 * 60,
    urgency: "high"
  });
  const response = await fetch(request.endpoint, {
    method: "POST",
    headers: request.headers,
    body: request.body
  });
  if (!response.ok && response.status !== 404 && response.status !== 410) {
    throw new Error(`Web Push failed with HTTP ${response.status}`);
  }
}

async function defaultDeliverTelegram(chatId: string, payload: NotificationPayload, env: Env, fetcher: Fetcher): Promise<void> {
  const textValue = `${payload.title}\n${payload.body}\n${payload.url}`;
  await sendTelegramMessage(fetcher, env, chatId, textValue);
}

async function sendTelegramMessage(fetcher: Fetcher, env: Env, chatId: string, textValue: string): Promise<void> {
  const response = await fetcher(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: textValue,
      disable_web_page_preview: false
    })
  });
  if (!response.ok) {
    throw new Error(`Telegram sendMessage failed with HTTP ${response.status}`);
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function generateToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

async function hashToken(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return base64Url(new Uint8Array(digest));
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function jsonResponse(body: unknown, status: number, headers: HeadersInit): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, "content-type": "application/json; charset=utf-8" }
  });
}

function cors(env: Env, origin: string): Record<string, string> {
  const allowed = env.ALLOWED_ORIGINS.split(",").map(row => row.trim()).filter(Boolean);
  const allowOrigin = allowed.includes(origin) ? origin : allowed[0] || "*";
  return {
    "access-control-allow-origin": allowOrigin,
    "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
    "access-control-allow-headers": "authorization,content-type,x-telegram-bot-api-secret-token",
    "access-control-max-age": "86400",
    vary: "Origin"
  };
}

export class MemoryStore implements Store {
  private devices = new Map<string, DeviceRecord>();
  private saved = new Map<string, Set<string>>();
  private push = new Map<string, WebPushSubscriptionRecord[]>();
  private telegram = new Map<string, TelegramLink>();
  private telegramSaved = new Map<string, Set<string>>();
  private pairings = new Map<string, { deviceId: string; expiresAt: string; usedAt?: string }>();
  private notifications = new Set<string>();

  async createDevice(rawToken: string): Promise<DeviceRecord> {
    const id = crypto.randomUUID ? crypto.randomUUID() : `device-${this.devices.size + 1}`;
    const device = { id, tokenHash: await hashToken(rawToken) };
    this.devices.set(id, device);
    return device;
  }

  async touchDevice(_deviceId: string): Promise<void> {}

  async getDevice(deviceId: string): Promise<DeviceRecord | null> {
    return this.devices.get(deviceId) || null;
  }

  async replaceSavedItems(deviceId: string, itemKeys: string[]): Promise<void> {
    this.saved.set(deviceId, new Set(itemKeys));
  }

  async savedItems(deviceId: string): Promise<string[]> {
    return [...(this.saved.get(deviceId) || new Set<string>())];
  }

  async upsertWebPushSubscription(deviceId: string, subscription: WebPushSubscriptionRecord): Promise<void> {
    this.push.set(deviceId, [subscription]);
  }

  async removeWebPushSubscriptions(deviceId: string): Promise<void> {
    this.push.set(deviceId, []);
  }

  async webPushSubscriptions(deviceId: string): Promise<WebPushSubscriptionRecord[]> {
    return this.push.get(deviceId) || [];
  }

  async createTelegramPairingToken(rawToken: string, deviceId: string, expiresAt: string): Promise<void> {
    this.pairings.set(await hashToken(rawToken), { deviceId, expiresAt });
  }

  async consumeTelegramPairingToken(rawToken: string, now: string): Promise<string | null> {
    const tokenHash = await hashToken(rawToken);
    const pairing = this.pairings.get(tokenHash);
    if (!pairing || pairing.usedAt || pairing.expiresAt < now) return null;
    pairing.usedAt = now;
    return pairing.deviceId;
  }

  async upsertTelegramLink(deviceId: string, link: TelegramLink): Promise<void> {
    this.telegram.set(deviceId, link);
  }

  async removeTelegramLink(deviceId: string): Promise<void> {
    this.telegram.delete(deviceId);
  }

  async telegramLink(deviceId: string): Promise<TelegramLink | null> {
    return this.telegram.get(deviceId) || null;
  }

  async telegramSavedItems(chatId: string): Promise<string[]> {
    return [...(this.telegramSaved.get(chatId) || new Set<string>())].sort();
  }

  async telegramLinkedDeviceCount(chatId: string): Promise<number> {
    return [...this.telegram.values()].filter(link => link.chatId === chatId).length;
  }

  async replaceTelegramSavedItems(chatId: string, itemKeys: string[]): Promise<void> {
    this.telegramSaved.set(chatId, new Set(itemKeys));
  }

  async mergeTelegramSavedItems(chatId: string, itemKeys: string[]): Promise<void> {
    const items = this.telegramSaved.get(chatId) || new Set<string>();
    for (const itemKey of itemKeys) items.add(itemKey);
    this.telegramSaved.set(chatId, items);
  }

  async telegramChatsWithSavedItem(itemKey: string): Promise<string[]> {
    const enabledChats = new Set([...this.telegram.values()].map(link => link.chatId));
    return [...this.telegramSaved.entries()]
      .filter(([chatId, items]) => enabledChats.has(chatId) && items.has(itemKey))
      .map(([chatId]) => chatId)
      .sort();
  }

  async devicesWithSavedItem(itemKey: string): Promise<string[]> {
    return [...this.saved.entries()].filter(([, items]) => items.has(itemKey)).map(([deviceId]) => deviceId);
  }

  async hasNotification(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string): Promise<boolean> {
    return this.notifications.has(notificationKey(stockUpdatedAt, itemKey, channel, targetHash));
  }

  async recordNotification(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string, _status: string): Promise<void> {
    this.notifications.add(notificationKey(stockUpdatedAt, itemKey, channel, targetHash));
  }

  async incrementRateLimit(_key: string, _windowStart: string): Promise<number> {
    return 1;
  }
}

class D1Store implements Store {
  constructor(private readonly db: D1Database) {}

  async createDevice(rawToken: string): Promise<DeviceRecord> {
    const id = crypto.randomUUID();
    const tokenHash = await hashToken(rawToken);
    const now = new Date().toISOString();
    await this.db.prepare(
      "insert into devices (id, token_hash, created_at, updated_at, last_seen_at) values (?, ?, ?, ?, ?)"
    ).bind(id, tokenHash, now, now, now).run();
    return { id, tokenHash };
  }

  async touchDevice(deviceId: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.prepare("update devices set updated_at = ?, last_seen_at = ? where id = ?").bind(now, now, deviceId).run();
  }

  async getDevice(deviceId: string): Promise<DeviceRecord | null> {
    const row = await this.db.prepare("select id, token_hash as tokenHash from devices where id = ?").bind(deviceId).first<DeviceRecord>();
    return row || null;
  }

  async replaceSavedItems(deviceId: string, itemKeys: string[]): Promise<void> {
    const now = new Date().toISOString();
    await this.db.batch([
      this.db.prepare("delete from saved_items where device_id = ?").bind(deviceId),
      ...itemKeys.map(itemKey => this.db.prepare("insert into saved_items (device_id, item_key, updated_at) values (?, ?, ?)").bind(deviceId, itemKey, now))
    ]);
  }

  async savedItems(deviceId: string): Promise<string[]> {
    const result = await this.db.prepare("select item_key as itemKey from saved_items where device_id = ? order by item_key").bind(deviceId).all<{ itemKey: string }>();
    return result.results.map(row => row.itemKey);
  }

  async upsertWebPushSubscription(deviceId: string, subscription: WebPushSubscriptionRecord): Promise<void> {
    const now = new Date().toISOString();
    await this.db.prepare(
      "insert into web_push_subscriptions (device_id, endpoint, p256dh, auth, user_agent, enabled, updated_at) values (?, ?, ?, ?, '', 1, ?) on conflict(endpoint) do update set device_id = excluded.device_id, p256dh = excluded.p256dh, auth = excluded.auth, enabled = 1, updated_at = excluded.updated_at"
    ).bind(deviceId, subscription.endpoint, subscription.p256dh, subscription.auth, now).run();
  }

  async removeWebPushSubscriptions(deviceId: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.prepare("update web_push_subscriptions set enabled = 0, updated_at = ? where device_id = ?").bind(now, deviceId).run();
  }

  async webPushSubscriptions(deviceId: string): Promise<WebPushSubscriptionRecord[]> {
    const result = await this.db.prepare(
      "select endpoint, p256dh, auth from web_push_subscriptions where device_id = ? and enabled = 1"
    ).bind(deviceId).all<WebPushSubscriptionRecord>();
    return result.results;
  }

  async createTelegramPairingToken(rawToken: string, deviceId: string, expiresAt: string): Promise<void> {
    await this.db.prepare(
      "insert into telegram_pairing_tokens (token_hash, device_id, expires_at, used_at) values (?, ?, ?, null)"
    ).bind(await hashToken(rawToken), deviceId, expiresAt).run();
  }

  async consumeTelegramPairingToken(rawToken: string, now: string): Promise<string | null> {
    const tokenHash = await hashToken(rawToken);
    const row = await this.db.prepare(
      "select device_id as deviceId from telegram_pairing_tokens where token_hash = ? and used_at is null and expires_at >= ?"
    ).bind(tokenHash, now).first<{ deviceId: string }>();
    if (!row) return null;
    await this.db.prepare("update telegram_pairing_tokens set used_at = ? where token_hash = ?").bind(now, tokenHash).run();
    return row.deviceId;
  }

  async upsertTelegramLink(deviceId: string, link: TelegramLink): Promise<void> {
    const now = new Date().toISOString();
    await this.db.prepare(
      "insert into telegram_links (device_id, chat_id, username, enabled, updated_at) values (?, ?, ?, 1, ?) on conflict(device_id) do update set chat_id = excluded.chat_id, username = excluded.username, enabled = 1, updated_at = excluded.updated_at"
    ).bind(deviceId, link.chatId, link.username || "", now).run();
  }

  async removeTelegramLink(deviceId: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.prepare("update telegram_links set enabled = 0, updated_at = ? where device_id = ?").bind(now, deviceId).run();
  }

  async telegramLink(deviceId: string): Promise<TelegramLink | null> {
    const row = await this.db.prepare(
      "select chat_id as chatId, username from telegram_links where device_id = ? and enabled = 1"
    ).bind(deviceId).first<TelegramLink>();
    return row || null;
  }

  async telegramSavedItems(chatId: string): Promise<string[]> {
    const result = await this.db.prepare(
      "select item_key as itemKey from telegram_saved_items where chat_id = ? order by item_key"
    ).bind(chatId).all<{ itemKey: string }>();
    return result.results.map(row => row.itemKey);
  }

  async telegramLinkedDeviceCount(chatId: string): Promise<number> {
    const row = await this.db.prepare(
      "select count(distinct device_id) as deviceCount from telegram_links where chat_id = ? and enabled = 1"
    ).bind(chatId).first<{ deviceCount: number }>();
    return row?.deviceCount || 0;
  }

  async replaceTelegramSavedItems(chatId: string, itemKeys: string[]): Promise<void> {
    const now = new Date().toISOString();
    await this.db.batch([
      this.db.prepare("delete from telegram_saved_items where chat_id = ?").bind(chatId),
      ...itemKeys.map(itemKey => this.db.prepare("insert into telegram_saved_items (chat_id, item_key, updated_at) values (?, ?, ?)").bind(chatId, itemKey, now))
    ]);
  }

  async mergeTelegramSavedItems(chatId: string, itemKeys: string[]): Promise<void> {
    if (!itemKeys.length) return;
    const now = new Date().toISOString();
    await this.db.batch(
      itemKeys.map(itemKey => this.db.prepare(
        "insert or ignore into telegram_saved_items (chat_id, item_key, updated_at) values (?, ?, ?)"
      ).bind(chatId, itemKey, now))
    );
  }

  async telegramChatsWithSavedItem(itemKey: string): Promise<string[]> {
    const result = await this.db.prepare(
      "select distinct tsi.chat_id as chatId from telegram_saved_items tsi join telegram_links tl on tl.chat_id = tsi.chat_id and tl.enabled = 1 where tsi.item_key = ? order by tsi.chat_id"
    ).bind(itemKey).all<{ chatId: string }>();
    return result.results.map(row => row.chatId);
  }

  async devicesWithSavedItem(itemKey: string): Promise<string[]> {
    const result = await this.db.prepare("select device_id as deviceId from saved_items where item_key = ?").bind(itemKey).all<{ deviceId: string }>();
    return result.results.map(row => row.deviceId);
  }

  async hasNotification(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string): Promise<boolean> {
    const row = await this.db.prepare(
      "select id from notification_log where stock_updated_at = ? and item_key = ? and channel = ? and target_hash = ? limit 1"
    ).bind(stockUpdatedAt, itemKey, channel, targetHash).first<{ id: number }>();
    return Boolean(row);
  }

  async recordNotification(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string, status: string, error?: string): Promise<void> {
    const now = new Date().toISOString();
    await this.db.prepare(
      "insert or ignore into notification_log (stock_updated_at, item_key, channel, target_hash, sent_at, status, error) values (?, ?, ?, ?, ?, ?, ?)"
    ).bind(stockUpdatedAt, itemKey, channel, targetHash, now, status, error || "").run();
  }

  async incrementRateLimit(key: string, windowStart: string): Promise<number> {
    const oldestWindow = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    await this.db.prepare("delete from rate_limits where window_start < ?").bind(oldestWindow).run();
    await this.db.prepare(
      "insert into rate_limits (key, window_start, request_count) values (?, ?, 1) on conflict(key, window_start) do update set request_count = request_count + 1"
    ).bind(key, windowStart).run();
    const row = await this.db.prepare(
      "select request_count as requestCount from rate_limits where key = ? and window_start = ?"
    ).bind(key, windowStart).first<{ requestCount: number }>();
    return row?.requestCount || 1;
  }
}

function notificationKey(stockUpdatedAt: string, itemKey: string, channel: string, targetHash: string): string {
  return `${stockUpdatedAt}|${itemKey}|${channel}|${targetHash}`;
}
