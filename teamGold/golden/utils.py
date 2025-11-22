from django.conf import settings

def is_local(author_id: str) -> bool:
    local_prefix = settings.SITE_URL.rstrip("/") + "/api/authors/"
    return str(author_id).startswith(local_prefix)