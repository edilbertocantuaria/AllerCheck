import {
  callUpstream,
  getAuthorizationHeader,
  jsonDetailError,
  toErrorResponseFromUpstream,
  toJsonResponse
} from "@/lib/api-route-utils";
import { HttpMethod, HttpStatus } from "@/lib/enums";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(request: Request, context: RouteContext) {
  const { id } = await context.params;
  const authHeader = getAuthorizationHeader(request);

  const upstreamResponse = await callUpstream({
    path: `/conversations/${id}`,
    method: HttpMethod.GET,
    authorization: authHeader,
    includeJsonContentType: true
  });

  if (!upstreamResponse) {
    return jsonDetailError(
      "Não foi possível conectar à API.",
      HttpStatus.BAD_GATEWAY,
      "UPSTREAM_UNREACHABLE"
    );
  }

  if (!upstreamResponse.ok) {
    return toErrorResponseFromUpstream(
      upstreamResponse,
      "Falha ao buscar conversa.",
      "UPSTREAM_CONVERSATIONS_ERROR"
    );
  }

  return toJsonResponse(upstreamResponse);
}

export async function DELETE(request: Request, context: RouteContext) {
  const { id } = await context.params;
  const authHeader = getAuthorizationHeader(request);

  const upstreamResponse = await callUpstream({
    path: `/conversations/${id}`,
    method: HttpMethod.DELETE,
    authorization: authHeader
  });

  if (!upstreamResponse) {
    return jsonDetailError(
      "Não foi possível conectar à API.",
      HttpStatus.BAD_GATEWAY,
      "UPSTREAM_UNREACHABLE"
    );
  }

  if (upstreamResponse.status === HttpStatus.NO_CONTENT) {
    return new Response(null, { status: HttpStatus.NO_CONTENT });
  }

  if (!upstreamResponse.ok) {
    return toErrorResponseFromUpstream(
      upstreamResponse,
      "Falha ao remover conversa.",
      "UPSTREAM_CONVERSATIONS_ERROR"
    );
  }

  return toJsonResponse(upstreamResponse);
}
