import uuid
from django.conf import settings
from urllib.parse import unquote, urlparse
from rest_framework.response import Response
from .models import Node
import requests
import json
from django.db import transaction
from .models import Author
import logging
from django.core.paginator import Paginator
from datetime import datetime, timezone


def notify(author, data):
    """
    Notify followers of `author` by POSTing `data` to each follower's node inbox.

    - `author` is an `Author` instance (the user whose followers should be notified)
    - `data` is a JSON-serializable payload to send (e.g. the comment/like/entry/activity object)

    - For each follower, derive the follower's host and look up a matching `Node`.
    - If a matching `Node` exists and is active, POST `data` to that node's `/inbox` URL
      using any HTTP auth configured on the `Node`.
    """
    logger = logging.getLogger(__name__)
    results = []

    # Use the reverse relation 'followers_set' to get Authors who follow `author`.
    try:
        followers_qs = author.followers_set.all()
    except Exception:
        logger.exception("Failed to get followers for author %s", getattr(author, 'id', None))
        return results

    for follower in followers_qs:
        try:
            # follower.id is an author's FQID, e.g. 'http://nodebbbb/api/authors/222/'
            parsed = urlparse(str(follower.id))
            if not parsed.scheme or not parsed.netloc:
                logger.debug("Skipping follower with invalid id: %s", follower.id)
                continue

            follower_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')

            # Look up a Node whose id starts with the follower's host
            node = Node.objects.filter(id__startswith=follower_base).first()
            if not node:
                logger.debug("No Node found for follower host %s (follower=%s)", follower_base, follower.id)
                continue
            if not getattr(node, 'is_active', False):
                logger.debug("Skipping inactive node %s for follower %s", node.id, follower.id)
                continue

            inbox_url = node.id.rstrip('/') + '/inbox'
            auth = None
            if getattr(node, 'auth_user', None):
                auth = (node.auth_user, node.auth_pass)

            logger.debug("Posting notification to follower %s inbox %s", follower.id, inbox_url)
            resp = requests.post(
                inbox_url,
                json=data,
                auth=auth,
                headers={'Content-Type': 'application/json'},
                timeout=5,
            )
            results.append((follower.id, resp.status_code))
            if not (200 <= resp.status_code < 300):
                logger.warning("Failed to notify follower %s at %s: %s", follower.id, inbox_url, resp.status_code)

        except Exception as e:
            logger.exception("Exception while notifying follower %s: %s", getattr(follower, 'id', None), e)
            results.append((getattr(follower, 'id', None), None))

    return results


def get_remote_author_profile(remote_node_url, author_id):
    url = f"{remote_node_url}/api/profile/{author_id}/"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

'''
Extracts remote node object from fqid (https://node1.com/api/authors/<uuid>/)
    will return node instance or None if host is local or not trusted
'''
def get_remote_node_from_fqid(fqid):
    if not fqid: return None
    fqid = unquote(str(fqid)).rstrip('/')
    try:
        parsed = urlparse(fqid)
        if not parsed.scheme or not parsed.netloc:
            return None
        remote_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    except Exception:
        return None
    if settings.LOCAL_NODE_URL == remote_base:
        return None

    node = Node.objects.filter(id__startswith=remote_base).first()
    if not node:
        return None
    if not node.is_active:
        return None
    return node

'''
create fqid (id) for comment
author.id is a already createdd fqid, so append to the end
'''
def generate_comment_fqid(author):
    comment_uuid = uuid.uuid4()
    return f"{author.id}/commented/{comment_uuid}"

def generate_like_fqid(author):
    like_uuid = uuid.uuid4()
    return f"{author.id}/liked/{like_uuid}"

'''
convert from fqid to uuid
'''
def fqid_to_uuid(fqid):
    unquoted_fqid = unquote(fqid)
    uid = unquoted_fqid.strip("/").split("/")[-1]
    return uid
'''
pagination for listing comments and likes
    params: allowed - filtered list of items 
    returns: page object that is input for the correct serializer
    (CommentSerializer(page_obj.object_list, many=True).data)
'''
def paginate(request, allowed):
    try:
        page_size = int(request.query_params.get('size', 10))
    except Exception:
        page_size = 10
    try:
        page_number = int(request.query_params.get('page', 1))
    except Exception:
        page_number = 1

    paginator = Paginator(allowed, page_size)
    page_obj = paginator.get_page(page_number)
    return page_obj


'''
checks if a node is remote by checking if its URL (id) is different from 
local nodes URL
'''
def is_remote_node(node):
    return node.id != settings.LOCAL_NODE_URL

def is_local(author_id: str) -> bool:
    """
    Returns True if the given author_id string belongs to this node.
    """
    local_prefix = settings.SITE_URL.rstrip("/") + "/api/authors/"
    return str(author_id).startswith(local_prefix)


# ! edited code 

def get_or_create_foreign_author(author_url):
    from .models import Author
    author, created = Author.objects.get_or_create(
        id=author_url,
        defaults={"displayName": author_url.split("/")[-2]}
    )
    return author

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
