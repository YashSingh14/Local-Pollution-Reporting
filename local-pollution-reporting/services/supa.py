import os
from supabase import create_client, Client
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

_client = None
_service_client = None


def get_client() -> "Client":
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _client


def get_service_client() -> "Client":
    global _service_client
    if _service_client is None:
        _service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _service_client


def public_url_for(bucket: str, path: str) -> str:
    client = get_client()
    return client.storage.from_(bucket).get_public_url(path)


def upsert_profile(client: "Client", user_id: str, display_name: str):
    client.table("profiles").upsert({
        "id": user_id,
        "display_name": display_name
    }, on_conflict="id").execute()


def mask_user_handle(user_id: str) -> str:
    if not user_id:
        return "usr_****"
    return f"usr_{user_id[:4]}****"
