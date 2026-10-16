import { NextResponse } from "next/server";
import { ActiveRequestTracker } from "@/lib/monitoring/activeRequests";

// We force dynamic because this returns live in-memory state
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  // Simple security check: Only allow requests from localhost
  const url = new URL(request.url);
  if (url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const activeRequests = ActiveRequestTracker.getActiveRequests();
  return NextResponse.json({ activeRequests });
}
