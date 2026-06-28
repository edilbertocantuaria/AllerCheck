const apiBaseUrl = process.env.API_BASE_URL;

if (!apiBaseUrl) {
  throw new Error("API_BASE_URL is not defined. Configure it in .env.");
}

const resolvedApiBaseUrl = apiBaseUrl;

export function getApiBaseUrl() {
  return resolvedApiBaseUrl.replace(/\/$/, "");
}
