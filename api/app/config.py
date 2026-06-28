from pinecone import Pinecone

from app.core.settings import get_settings

settings = get_settings()

OPENAI_API_KEY = settings.openai_api_key
PINECONE_API_KEY = settings.pinecone_api_key
INDEX_NAME = settings.index_name
DATABASE_URL = settings.database_url
GOOGLE_CLIENT_ID = settings.google_client_id


class _LazyPineconeClient:
    def __init__(self, api_key: str | None):
        self._api_key = api_key
        self._client: Pinecone | None = None

    def _resolve(self) -> Pinecone:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("PINECONE_API_KEY is not configured.")
            self._client = Pinecone(api_key=self._api_key)
        return self._client

    def __getattr__(self, item):
        return getattr(self._resolve(), item)


pinecone_client = _LazyPineconeClient(PINECONE_API_KEY)
