const POLL_INTERVAL_MS = 1000;
const BASE_URL = process.env.OMNIROUTE_MONITOR_BASE_URL || "http://127.0.0.1:20128";
const ENDPOINT = new URL("/v1/explain/routing?limit=50", BASE_URL);

async function fetchRoutingEvents() {
  const headers = process.env.OMNIROUTE_API_KEY
    ? { Authorization: `Bearer ${process.env.OMNIROUTE_API_KEY}` }
    : {};
  const response = await fetch(ENDPOINT, { headers, cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${ENDPOINT}`);
  }
  return response.json();
}

async function render() {
  try {
    const data = await fetchRoutingEvents();
    const events = data.events || [];

    // Clear terminal (cross-platform)
    process.stdout.write("\x1Bc");

    console.log(`\x1b[36m=== OmniRoute Recent Routing Decisions ===\x1b[0m`);
    console.log(`Gateway: ${BASE_URL} | Refresh: ${POLL_INTERVAL_MS / 1000}s\n`);

    if (events.length === 0) {
      console.log("No routing events yet. Send a request through OmniRoute.");
    } else {
      console.log(`Recent events: ${events.length}\n`);

      const modelCounts = {};
      const tableData = events.slice(-15).reverse().map((event) => {
        const model = `${event.provider}/${event.model}`;
        modelCounts[model] = (modelCounts[model] || 0) + 1;
        return {
          Time: new Date(event.ts).toLocaleTimeString(),
          Model: model,
          Strategy: event.strategy,
          Status: event.status,
          Outcome: event.outcome,
          "Latency ms": event.latencyMs,
          Retries: event.retries,
          Fallback: event.fallbackUsed ? "yes" : "no",
        };
      });

      console.log("\x1b[33m--- Latest Completed Requests ---\x1b[0m");
      console.table(tableData);

      console.log("\n\x1b[33m--- Models in Latest 15 Requests ---\x1b[0m");
      console.table(Object.entries(modelCounts).map(([Model, Count]) => ({ Model, Count })));
    }
  } catch (err) {
    process.stdout.write("\x1Bc");
    console.log(`\x1b[31mCannot read routing events: ${err.message}\x1b[0m`);
    console.log(`Check the gateway URL and API key for ${BASE_URL}.`);
  }
}

// Initial render immediately, then poll
render();
setInterval(render, POLL_INTERVAL_MS);
