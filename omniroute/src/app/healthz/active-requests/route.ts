import { NextResponse } from "next/server";
import { ActiveRequestTracker } from "@/lib/monitoring/activeRequests";

// We force dynamic because this returns live in-memory state
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const activeRequests = ActiveRequestTracker.getActiveRequests();
  return NextResponse.json({ activeRequests });
}
