import assert from "node:assert/strict";
import { Readable } from "node:stream";
import { test } from "node:test";
import { createRequestHandler } from "../src/server.js";

const fixedNow = "2026-05-11T00:00:00.000Z";
const handler = createRequestHandler({
  now: () => new Date(fixedNow)
});

test("GET /health returns ok", async () => {
  const response = await invoke("GET", "/health");

  assert.equal(response.status, 200);
  assert.deepEqual(response.body, { ok: true });
});

test("POST /api/widgets creates a widget", async () => {
  const response = await invoke("POST", "/api/widgets", { name: "alpha" });

  assert.equal(response.status, 201);
  assert.deepEqual(response.body, {
    widget: {
      id: "1",
      name: "alpha",
      createdAt: fixedNow
    }
  });
});

test("POST /api/widgets rejects missing names", async () => {
  const response = await invoke("POST", "/api/widgets", { name: " " });

  assert.equal(response.status, 400);
  assert.equal(response.body.error, "invalid_widget");
});

test("unknown routes return 404", async () => {
  const response = await invoke("GET", "/missing");

  assert.equal(response.status, 404);
  assert.equal(response.body.error, "not_found");
});

async function invoke(method, url, body) {
  const req = Readable.from(body === undefined ? [] : [JSON.stringify(body)]);
  req.method = method;
  req.url = url;

  let status = 200;
  let payload = "";

  const res = {
    writeHead(statusCode) {
      status = statusCode;
    },
    end(chunk) {
      payload = chunk;
    }
  };

  await handler(req, res);

  return {
    status,
    body: JSON.parse(payload)
  };
}
