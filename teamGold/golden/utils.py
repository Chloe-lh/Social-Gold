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

# TODO 
def send_new_entry(entry):
    """
    Sends a newly created entry to all remote followers and friends.
    UserStory #20
    """
    author = entry.author

    # Followers where this author is the "object"
    followers = Follow.objects.filter(object=author.id, state="ACCEPTED")

    for follow in followers:
        follower = follow.actor

        if follower.host.startswith(settings.SITE_URL):
            continue

        # Determine node for auth (matching host)
        node = Node.objects.filter(id__contains=follower.host).first()

        activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Create",
            "actor": {"id": author.id},
            "object": entry.to_activitypub_dict(),
        }

    return activity