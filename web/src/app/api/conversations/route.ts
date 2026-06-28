import {
  callUpstream,
  getAuthorizationHeader,
  jsonDetailError,
  parseJsonBody,
  toErrorResponseFromUpstream,
  toJsonResponse
} from "@/lib/api-route-utils";
import { HttpMethod, HttpStatus } from "@/lib/enums";

interface CreateConversationPayload {
  title?: string | null;
}

export async function GET(request: Request) {
  const authHeader = getAuthorizationHeader(request);

  const upstreamResponse = await callUpstream({
    path: "/conversations",
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
      "Falha ao listar conversas.",
      "UPSTREAM_CONVERSATIONS_ERROR"
    );
  }

  return toJsonResponse(upstreamResponse);
}

export async function POST(request: Request) {
  const authHeader = getAuthorizationHeader(request);

  const payload = (await parseJsonBody<CreateConversationPayload>(request)) || {
    title: null
  };

  const upstreamResponse = await callUpstream({
    path: "/conversations",
    method: HttpMethod.POST,
    authorization: authHeader,
    includeJsonContentType: true,
    body: payload
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
      "Falha ao criar conversa.",
      "UPSTREAM_CONVERSATIONS_ERROR"
    );
  }

  return toJsonResponse(upstreamResponse);
}
