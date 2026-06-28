import {
  callUpstream,
  jsonDetailError,
  parseJsonBody,
  toErrorResponseFromUpstream,
  toJsonResponse
} from "@/lib/api-route-utils";
import { HttpMethod, HttpStatus } from "@/lib/enums";

interface RegisterPayload {
  email: string;
  password: string;
}

export async function POST(request: Request) {
  const payload = await parseJsonBody<RegisterPayload>(request);

  if (!payload) {
    return jsonDetailError(
      "Corpo da requisição inválido.",
      HttpStatus.BAD_REQUEST,
      "INVALID_REQUEST_BODY"
    );
  }

  const upstreamResponse = await callUpstream({
    path: "/auth/register",
    method: HttpMethod.POST,
    body: payload,
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
      "Falha no registro.",
      "UPSTREAM_AUTH_ERROR"
    );
  }

  return toJsonResponse(upstreamResponse);
}
