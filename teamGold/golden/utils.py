import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from .models import Author, Node, Follow, Entry
from django.utils import timezone

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

def send_new_entry(entry):
    """
    Sends a newly created entry to all remote followers.
    UserStory #20
    """
    author = entry.author
    followers = Follow.objects.filter(object=author, state="ACCEPTED").select_related("actor")

    results = []

    for follow in followers:
        follower = follow.actor

        if follower.host.startswith(settings.SITE_URL):
            continue

        node = Node.objects.filter(id__contains=follower.host).first()

        activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Create",
            "actor": {"id": author.id},
            "object": entry.to_activitypub_dict(),
        }

        inbox_url = getattr(follower, "inbox", None)
        if not inbox_url:
            # fall back to prevent crashing
            inbox_url = follower.id.rstrip("/") + "/inbox/"

        success = post_to_remote_inbox(inbox_url, activity, node=node)
        results.append((follower.id, success))

    return results

def user_follows_author(local_author, target_author):
    return Follow.objects.filter(
        actor=local_author,
        object=target_author.id,
        state="ACCEPTED"
    ).exists()

def sync_remote_entries(node, local_user_author):
    items = fetch_remote_entries(node)
    synced_entries = []

    for item in items:
        author_data = item.get("author", {})
        author_id = author_data.get("id")

        if not author_id:
            continue

        if not Follow.objects.filter(
            actor=local_user_author,
            object=author_id,
            state="ACCEPTED"
        ).exists():
            continue

        entry = sync_remote_entry(item, node)
        if entry:
            synced_entries.append(entry)

    return synced_entries

def fetch_remote_entries(node, timeout=5):
    url = f"{node.id.rstrip('/')}/api/entries/"

    auth = None
    if node.auth_user:
        auth = HTTPBasicAuth(node.auth_user, node.auth_pass)

    try:
        r = requests.get(url, auth=auth, timeout=timeout)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("items", [])
    except requests.RequestException:
        return []

def sync_remote_entry(item, node):
    entry_id = item.get("id")
    if not entry_id:
        return None

    author_data = item.get("author", {})
    author_id = author_data.get("id")

    if not author_id:
        return None

    foreign_author, _ = Author.objects.get_or_create(
        id=author_id,
        defaults={
            "username": author_data.get("displayName", "Unknown"),
            "host": author_data.get("host", node.id),
        }
    )

    defaults = {
        "author": foreign_author,
        "title": item.get("title", ""),
        "content": item.get("content", ""),
        "contentType": item.get("contentType", "text/plain"),
        "visibility": item.get("visibility", "PUBLIC"),
        "origin": item.get("origin") or item.get("id"),
        "source": item.get("source") or item.get("id"),
        "published": item.get("published") or timezone.now(),
        "is_posted": timezone.now(),
    }

    entry, _ = Entry.objects.update_or_create(
        id=entry_id,
        defaults=defaults
    )

    return entry

def send_update_activity(entry):
    """
    Sends an ActivityPub 'Update' activity to all remote followers.
    Used when a local Entry is edited.
    """
    author = entry.author
    followers = Follow.objects.filter(object=author, state="ACCEPTED").select_related("actor")

    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Update",
        "actor": {"id": author.id},
        "object": entry.to_activitypub_dict(),
    }

    results = []

    for follow in followers:
        follower = follow.actor

        # Skip local followers
        if follower.host.startswith(settings.SITE_URL):
            continue

        node = Node.objects.filter(id__contains=follower.host).first()

        # Get inbox for remote follower
        inbox_url = getattr(follower, "inbox", None)
        if not inbox_url:
            inbox_url = follower.id.rstrip("/") + "/inbox/"

        success = post_to_remote_inbox(inbox_url, activity, node=node)
        results.append((follower.id, success))

    return results
