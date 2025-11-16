import requests
from requests.auth import HTTPBasicAuth
from .models import Author, Node

def get_or_create_foreign_author(author_url):
    from .models import Author
    author, created = Author.objects.get_or_create(
        id=author_url,
        defaults={"displayName": author_url.split("/")[-2]}
    )
    return author

def post_to_remote_inbox(inbox_url, payload, node=None, timeout=5):
    auth = None
    if node and node.auth_user:
        auth = HTTPBasicAuth(node.auth_user, node.auth_pass)
    try:
        resp = requests.post(inbox_url, json=payload, auth=auth, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        # log failure; do not raise in utils (let caller decide)
        return False
    return True

def build_accept_activity(local_actor_url, remote_actor_url, summary=""):
    return {
        "type": "accept",
        "summary": summary,
        "actor": {"id": local_actor_url},
        "object": {"id": remote_actor_url}
    }
