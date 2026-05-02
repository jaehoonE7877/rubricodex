import http from "node:http";

export function createApp() {
  return http.createServer(createRequestHandler());
}

export function createRequestHandler() {
  const widgets = new Map();
  let nextId = 1;

  return async function handleRequest(req, res) {
    try {
      if (req.method === "GET" && req.url === "/health") {
        return sendJson(res, 200, { ok: true });
      }

      if (req.method === "POST" && req.url === "/api/widgets") {
        const body = await readJson(req);

        if (!body || typeof body.name !== "string" || body.name.trim() === "") {
          return sendJson(res, 400, {
            error: "invalid_widget",
            message: "name is required"
          });
        }

        const widget = {
          id: String(nextId++),
          name: body.name.trim()
        };

        widgets.set(widget.id, widget);
        return sendJson(res, 201, { widget });
      }

      return sendJson(res, 404, { error: "not_found" });
    } catch {
      return sendJson(res, 400, {
        error: "invalid_json",
        message: "request body must be valid JSON"
      });
    }
  };
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let data = "";

    req.setEncoding("utf8");
    req.on("data", chunk => {
      data += chunk;
    });
    req.on("end", () => {
      if (data.trim() === "") {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(data));
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);

  res.writeHead(statusCode, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body)
  });
  res.end(body);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.PORT || 3000);
  createApp().listen(port, () => {
    console.log(`source-code-endpoint fixture listening on ${port}`);
  });
}
