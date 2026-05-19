import { describe, expect, it, vi } from "vitest";
import { createApp, MemoryStore, type Env, type StockEventPayload } from "../src/app";

function env(overrides: Partial<Env> = {}): Env {
  return {
    ALLOWED_ORIGINS: "https://bitworks-io.github.io,http://localhost:8000",
    VAPID_PUBLIC_KEY: "public-vapid-key",
    VAPID_PRIVATE_KEY: "private-vapid-key",
    VAPID_SUBJECT: "mailto:alerts@example.com",
    TELEGRAM_BOT_USERNAME: "GigaPartsFilamentAlertsBot",
    TELEGRAM_BOT_TOKEN: "telegram-token",
    TELEGRAM_WEBHOOK_SECRET: "telegram-secret",
    STOCK_EVENT_TOKEN: "stock-token",
    ...overrides
  };
}

async function json(response: Response) {
  return response.json() as Promise<Record<string, unknown>>;
}

function telegramText(fetcher: ReturnType<typeof vi.fn>, index: number): string {
  const init = fetcher.mock.calls[index]?.[1] as RequestInit | undefined;
  return JSON.parse(String(init?.body || "{}")).text;
}

describe("notification worker app", () => {
  it("registers an anonymous device and authenticates saved item sync", async () => {
    const store = new MemoryStore();
    const app = createApp({ store });
    const deviceResponse = await app.fetch(new Request("https://worker.test/api/devices", { method: "POST" }), env());
    expect(deviceResponse.status).toBe(201);
    const device = await json(deviceResponse);

    const savedResponse = await app.fetch(
      new Request(`https://worker.test/api/devices/${device.deviceId}/saved-items`, {
        method: "PUT",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${device.deviceToken}`
        },
        body: JSON.stringify({ itemKeys: ["Bambu|PLA Basic|123", "Polymaker|PETG|sku-1"] })
      }),
      env()
    );

    expect(savedResponse.status).toBe(204);
    expect(await store.savedItems(String(device.deviceId))).toEqual(["Bambu|PLA Basic|123", "Polymaker|PETG|sku-1"]);
  });

  it("rejects device updates with the wrong token", async () => {
    const store = new MemoryStore();
    const app = createApp({ store });
    const deviceResponse = await app.fetch(new Request("https://worker.test/api/devices", { method: "POST" }), env());
    const device = await json(deviceResponse);

    const response = await app.fetch(
      new Request(`https://worker.test/api/devices/${device.deviceId}/saved-items`, {
        method: "PUT",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer wrong-token"
        },
        body: JSON.stringify({ itemKeys: ["Bambu|PLA Basic|123"] })
      }),
      env()
    );

    expect(response.status).toBe(401);
  });

  it("stores and removes web push subscriptions for a device", async () => {
    const store = new MemoryStore();
    const app = createApp({ store });
    const deviceResponse = await app.fetch(new Request("https://worker.test/api/devices", { method: "POST" }), env());
    const device = await json(deviceResponse);
    const subscription = {
      endpoint: "https://push.example/send/1",
      keys: { p256dh: "p256dh-key", auth: "auth-key" }
    };

    const addResponse = await app.fetch(
      new Request(`https://worker.test/api/devices/${device.deviceId}/web-push-subscription`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${device.deviceToken}`
        },
        body: JSON.stringify({ subscription })
      }),
      env()
    );
    expect(addResponse.status).toBe(204);
    expect(await store.webPushSubscriptions(String(device.deviceId))).toHaveLength(1);

    const deleteResponse = await app.fetch(
      new Request(`https://worker.test/api/devices/${device.deviceId}/web-push-subscription`, {
        method: "DELETE",
        headers: { authorization: `Bearer ${device.deviceToken}` }
      }),
      env()
    );
    expect(deleteResponse.status).toBe(204);
    expect(await store.webPushSubscriptions(String(device.deviceId))).toHaveLength(0);
  });

  it("pairs Telegram through a one-time start token", async () => {
    const store = new MemoryStore();
    const telegram = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const app = createApp({ store, fetcher: telegram });
    const deviceResponse = await app.fetch(new Request("https://worker.test/api/devices", { method: "POST" }), env());
    const device = await json(deviceResponse);

    const linkResponse = await app.fetch(
      new Request(`https://worker.test/api/devices/${device.deviceId}/telegram-link`, {
        method: "POST",
        headers: { authorization: `Bearer ${device.deviceToken}` }
      }),
      env()
    );
    expect(linkResponse.status).toBe(200);
    const link = await json(linkResponse);
    const token = String(link.pairingToken);

    const webhookResponse = await app.fetch(
      new Request("https://worker.test/telegram/webhook", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-telegram-bot-api-secret-token": "telegram-secret"
        },
        body: JSON.stringify({ message: { chat: { id: 12345, username: "maker" }, text: `/start ${token}` } })
      }),
      env()
    );

    expect(webhookResponse.status).toBe(204);
    expect(await store.telegramLink(String(device.deviceId))).toMatchObject({ chatId: "12345", username: "maker" });
    expect(telegram).toHaveBeenCalledOnce();
    expect(telegramText(telegram, 0)).toContain("Telegram is connected");
    expect(telegramText(telegram, 0)).toContain("/list");
    expect(telegramText(telegram, 0)).toContain("0 saved");

    const replayResponse = await app.fetch(
      new Request("https://worker.test/telegram/webhook", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-telegram-bot-api-secret-token": "telegram-secret"
        },
        body: JSON.stringify({ message: { chat: { id: 12345 }, text: `/start ${token}` } })
      }),
      env()
    );
    expect(replayResponse.status).toBe(204);
    expect(telegram).toHaveBeenCalledTimes(2);
  });

  it("answers Telegram list, status, help, and unknown commands", async () => {
    const store = new MemoryStore();
    const telegram = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const app = createApp({ store, fetcher: telegram });
    const device = await store.createDevice("device-token");
    await store.replaceSavedItems(device.id, ["Bambu|PLA Basic|SKU123", "Polymaker|PETG|sku-1"]);
    await store.upsertTelegramLink(device.id, { chatId: "12345", username: "maker" });
    await store.mergeTelegramSavedItems("12345", await store.savedItems(device.id));

    for (const text of ["/list", "/status", "/help", "/wat"]) {
      const response = await app.fetch(
        new Request("https://worker.test/telegram/webhook", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-telegram-bot-api-secret-token": "telegram-secret"
          },
          body: JSON.stringify({ message: { chat: { id: 12345, username: "maker" }, text } })
        }),
        env()
      );
      expect(response.status).toBe(204);
    }

    expect(telegramText(telegram, 0)).toContain("Saved filament list (2 items)");
    expect(telegramText(telegram, 0)).toContain("Bambu - PLA Basic - SKU123");
    expect(telegramText(telegram, 0)).toContain("Polymaker - PETG - sku-1");
    expect(telegramText(telegram, 1)).toContain("Connected");
    expect(telegramText(telegram, 1)).toContain("2 saved");
    expect(telegramText(telegram, 2)).toContain("/list");
    expect(telegramText(telegram, 3)).toContain("I do not understand that command");
  });

  it("uses a Telegram chat as a portable saved list across devices", async () => {
    const store = new MemoryStore();
    const telegram = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const app = createApp({ store, fetcher: telegram });
    const firstDevice = await store.createDevice("first-token");
    const secondDevice = await store.createDevice("second-token");
    await store.replaceSavedItems(firstDevice.id, ["Bambu|PLA Basic|123"]);

    await store.upsertTelegramLink(firstDevice.id, { chatId: "12345", username: "maker" });
    await store.mergeTelegramSavedItems("12345", await store.savedItems(firstDevice.id));
    await store.upsertTelegramLink(secondDevice.id, { chatId: "12345", username: "maker" });

    const statusResponse = await app.fetch(
      new Request(`https://worker.test/api/devices/${secondDevice.id}/telegram-link`, {
        method: "GET",
        headers: { authorization: "Bearer second-token" }
      }),
      env()
    );
    expect(statusResponse.status).toBe(200);
    expect(await json(statusResponse)).toMatchObject({
      linked: true,
      itemKeys: ["Bambu|PLA Basic|123"]
    });

    const replaceResponse = await app.fetch(
      new Request(`https://worker.test/api/devices/${secondDevice.id}/saved-items`, {
        method: "PUT",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer second-token"
        },
        body: JSON.stringify({ itemKeys: ["Polymaker|PETG|sku-1"] })
      }),
      env()
    );
    expect(replaceResponse.status).toBe(204);
    expect(await store.telegramSavedItems("12345")).toEqual(["Polymaker|PETG|sku-1"]);

    const deliveries: Array<{ channel: string; body: string }> = [];
    const deliveryApp = createApp({
      store,
      deliverTelegram: async (_chatId, payload) => {
        deliveries.push({ channel: "telegram", body: payload.body });
      }
    });
    const eventResponse = await deliveryApp.fetch(
      new Request("https://worker.test/api/stock-events", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer stock-token" },
        body: JSON.stringify({
          updatedAt: "2026-05-18T14:00:00Z",
          changes: {
            inStock: [
              { key: "Bambu|PLA Basic|123", brand: "Bambu", line: "PLA Basic", name: "Red" },
              { key: "Polymaker|PETG|sku-1", brand: "Polymaker", line: "PETG", name: "Blue" }
            ]
          }
        })
      }),
      env()
    );
    expect(eventResponse.status).toBe(202);
    expect(deliveries).toEqual([{ channel: "telegram", body: "Blue" }]);
  });

  it("delivers saved stock events to web push and Telegram once", async () => {
    const store = new MemoryStore();
    const deliveries: Array<{ channel: string; title: string; body: string; url: string }> = [];
    const app = createApp({
      store,
      deliverWebPush: async (_subscription, payload) => {
        deliveries.push({ channel: "web-push", ...payload });
      },
      deliverTelegram: async (_chatId, payload) => {
        deliveries.push({ channel: "telegram", ...payload });
      }
    });
    const device = await store.createDevice("device-token");
    await store.replaceSavedItems(device.id, ["Bambu|PLA Basic|123"]);
    await store.upsertWebPushSubscription(device.id, {
      endpoint: "https://push.example/send/1",
      p256dh: "p256dh-key",
      auth: "auth-key"
    });
    await store.upsertTelegramLink(device.id, { chatId: "12345", username: "maker" });
    await store.mergeTelegramSavedItems("12345", await store.savedItems(device.id));
    const payload: StockEventPayload = {
      updatedAt: "2026-05-18T12:00:00Z",
      changes: {
        inStock: [
          { key: "Bambu|PLA Basic|123", brand: "Bambu", line: "PLA Basic", name: "Red", sku: "SKU123", url: "https://example.com/red" },
          { key: "Bambu|PETG|999", brand: "Bambu", line: "PETG", name: "Blue", sku: "SKU999", url: "https://example.com/blue" }
        ]
      }
    };

    const first = await app.fetch(
      new Request("https://worker.test/api/stock-events", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer stock-token" },
        body: JSON.stringify(payload)
      }),
      env()
    );
    expect(first.status).toBe(202);
    expect(deliveries.map(row => row.channel)).toEqual(["web-push", "telegram"]);
    expect(deliveries.every(row => row.title.includes("Bambu"))).toBe(true);

    const second = await app.fetch(
      new Request("https://worker.test/api/stock-events", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer stock-token" },
        body: JSON.stringify(payload)
      }),
      env()
    );
    expect(second.status).toBe(202);
    expect(deliveries).toHaveLength(2);
  });

  it("bounds request bodies and sanitizes stock event URLs before delivery", async () => {
    const store = new MemoryStore();
    const deliveries: Array<{ channel: string; url: string }> = [];
    const app = createApp({
      store,
      deliverWebPush: async (_subscription, payload) => {
        deliveries.push({ channel: "web-push", url: payload.url });
      }
    });
    const device = await store.createDevice("device-token");
    await store.replaceSavedItems(device.id, ["Bambu|PLA Basic|123"]);
    await store.upsertWebPushSubscription(device.id, {
      endpoint: "https://push.example/send/1",
      p256dh: "p256dh-key",
      auth: "auth-key"
    });

    const tooLarge = await app.fetch(
      new Request(`https://worker.test/api/devices/${device.id}/saved-items`, {
        method: "PUT",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer device-token",
          "content-length": String(70 * 1024)
        },
        body: JSON.stringify({ itemKeys: [] })
      }),
      env()
    );
    expect(tooLarge.status).toBe(413);

    const response = await app.fetch(
      new Request("https://worker.test/api/stock-events", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: "Bearer stock-token" },
        body: JSON.stringify({
          updatedAt: "2026-05-18T13:00:00Z",
          changes: {
            inStock: [
              { key: "Bambu|PLA Basic|123", brand: "Bambu", line: "PLA Basic", name: "Red", url: "javascript:alert(1)" }
            ]
          }
        })
      }),
      env()
    );

    expect(response.status).toBe(202);
    expect(deliveries).toEqual([{ channel: "web-push", url: "https://bitworks-io.github.io/gigaparts-filament-stock/" }]);
  });
});
