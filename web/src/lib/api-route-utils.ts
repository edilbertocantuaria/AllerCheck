import { getApiBaseUrl } from "@/lib/api-base-url";
import { CacheMode, HttpMethod, HttpStatus } from "@/lib/enums";

export interface ApiErrorResponse {
  error?: string;
  detail?: string;
  code: string;
}

export function jsonDetailError(
  message: string,
  status: HttpStatus,
  code: string
) {
  return Response.json({ detail: message, code } satisfies ApiErrorResponse, {
    status
  });
}

export function jsonError(message: string, status: HttpStatus, code: string) {
  return Response.json({ error: message, code } satisfies ApiErrorResponse, {
    status
  });
}

export function getAuthorizationHeader(request: Request) {
  return request.headers.get("Authorization") || "";
}

export async function parseJsonBody<T>(request: Request): Promise<T | null> {
  try {
    return (await request.json()) as T;
  } catch {
    return null;
  }
}

export async function callUpstream(args: {
  path: string;
  method: HttpMethod;
  body?: unknown;
  authorization?: string;
  includeJsonContentType?: boolean;
}) {
  const headers: HeadersInit = {};

  if (args.includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }

  if (args.authorization) {
    headers.Authorization = args.authorization;
  }

  return fetch(`${getApiBaseUrl()}${args.path}`, {
    method: args.method,
    headers,
    body: args.body === undefined ? undefined : JSON.stringify(args.body),
    cache: CacheMode.NO_STORE
  }).catch(() => null);
}

export async function toJsonResponse(upstream: Response) {
  const payload = await upstream.json();
  return Response.json(payload, { status: upstream.status });
}

export async function toErrorResponseFromUpstream(
  upstream: Response,
  fallbackMessage: string,
  code: string
) {
  try {
    const payload = (await upstream.json()) as ApiErrorResponse;
    return Response.json(payload, { status: upstream.status });
  } catch {
    const text = await upstream.text();
    return jsonError(
      text || fallbackMessage,
      upstream.status as HttpStatus,
      code
    );
  }
}
