export interface ActiveRequest {
  id: string;
  user: string;
  model: string;
  startTime: number;
}

class Tracker {
  private requests = new Map<string, ActiveRequest>();

  addRequest(id: string, user: string, model: string) {
    this.requests.set(id, { id, user, model, startTime: Date.now() });
  }

  removeRequest(id: string) {
    this.requests.delete(id);
  }

  updateModel(id: string, model: string) {
    const req = this.requests.get(id);
    if (req) {
      req.model = model;
    }
  }

  getActiveRequests() {
    return Array.from(this.requests.values());
  }
}

export const ActiveRequestTracker = new Tracker();

export function withRequestTracking(id: string, response: Response) {
  // Extract actual routed provider/model from headers if OmniRoute set them
  const provider = response.headers.get("x-omniroute-provider");
  const model = response.headers.get("x-omniroute-model");
  
  if (provider || model) {
    const resolvedModel = [provider, model].filter(Boolean).join("/");
    ActiveRequestTracker.updateModel(id, resolvedModel);
  }

  if (!response.body) {
    ActiveRequestTracker.removeRequest(id);
    return response;
  }
  const transform = new TransformStream({
    flush() {
      ActiveRequestTracker.removeRequest(id);
    },
    cancel() {
      ActiveRequestTracker.removeRequest(id);
    }
  });
  return new Response(response.body.pipeThrough(transform), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
