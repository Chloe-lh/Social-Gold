# golden/services.py
from django.db import transaction
from .models import Author
from .utils import is_local 
import logging
from datetime import timezone
from urllib.parse import unquote, urlparse
import uuid
import requests
from django.conf import settings
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

def get_or_create_foreign_author(fqid: str, host: str = None, username: str = None):
    """
    Ensures a remote author exists locally.
    example: https://node3.herokuapp.com/api/authors/abc123-uuid

    Args:
        fqid: Full Qualified ID (FQID) of the author, e.g. "https://node.com/api/authors/uuid"
              Can also be just a UUID if host is provided
        host: Optional host URL to use if fqid is just a UUID
        username: Optional username to use instead of guessing from FQID
    """
    author = Author.objects.filter(id=fqid).first()
    if author:
        if username and author.username != username:
            author.username = username
            author.save()
        return author
    
    if username:
        is_local_author = is_local(fqid) if fqid.startswith('http') else (host is None or host == settings.SITE_URL.rstrip('/'))
        
        existing = Author.objects.filter(username=username).first()
        if existing:
            if existing.id != fqid:
                logger.warning(f"Found author '{username}' with different ID: {existing.id} vs {fqid}")
                if is_local(existing.id) and is_local_author:
                    if not fqid.startswith('http') and host:
                        full_fqid = f"{settings.SITE_URL.rstrip('/')}/api/authors/{fqid}"
                        if full_fqid != existing.id:
                            logger.warning(f"Author '{username}' exists but IDs don't match. Using existing: {existing.id}")
            return existing
    
    if "/api/authors/" in fqid or fqid.startswith("http"):
        full_fqid = fqid.rstrip("/")
        host = host or full_fqid.split("/api/authors/")[0]
        guessed_username = username or full_fqid.split("/")[-1]
        author_id = full_fqid
    elif host:
        uuid_part = fqid.rstrip("/")
        host = host.rstrip("/")
        author_id = f"{host}/api/authors/{uuid_part}"
        guessed_username = username or uuid_part
    else:
        logger.error(f"Cannot create foreign author: invalid FQID format '{fqid}', host='{host}'")
        return None
    
    author = Author.objects.create(
        id=author_id,
        username=guessed_username or "Unknown",
        host=host,
        is_approved=True,
    )

    return author

def generate_comment_fqid(author):
    """
    Create FQID for a comment related to the author.
    """
    comment_uuid = uuid.uuid4()
    return f"{author.id}/commented/{comment_uuid}"

def generate_like_fqid(author):
    """
    Create FQID for a like related to the author.
    """
    like_uuid = uuid.uuid4()
    return f"{author.id}/liked/{like_uuid}"

def fqid_to_uuid(fqid):
    """
    Convert a full FQID to UUID.
    """
    if not fqid:
        return None
    unquoted_fqid = unquote(str(fqid))
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

def sync_remote_entry(remote_entry, node):
    """
    Sync a remote entry (fetched from a node) with the local database.

    :param remote_entry: The entry data retrieved from the remote node.
    :param node: The remote node where the entry was fetched.
    :return: The local Entry object, or None if the sync failed.
    """
    try:
        entry_id = remote_entry.get('id')
        title = remote_entry.get('title', '')
        content = remote_entry.get('content', '')
        author_data = remote_entry.get('author', {})
        author_id = author_data.get('id')
        
        # Assuming you have a function to get or create an author
        author = Author.objects.get(id=author_id)

        # Create or update the entry
        entry, created = Entry.objects.update_or_create(
            id=entry_id,
            defaults={
                'author': author,
                'title': title,
                'content': content,
                'visibility': 'PUBLIC', 
            }
        )
        
        return entry
    except Exception as e:
        print(f"Error syncing remote entry: {e}")
        return None
    
def fetch_remote_entries(node, timeout=5):
    """
    Fetch entries from a remote node's API.

    :param node: The Node instance representing the remote server.
    :param timeout: Timeout duration for the HTTP request.
    :return: A list of remote entries (parsed JSON response).
    """
    try:
        # Construct the URL for the entries API endpoint on the remote node
        url = f"{node.id.rstrip('/')}/api/entries/"

        # If the node has authentication details, use them
        auth = None
        if node.auth_user:
            auth = (node.auth_user, node.auth_pass)

        # Send GET request to fetch entries
        response = requests.get(url, auth=auth, timeout=timeout, headers={"Accept": "application/json"})

        # If successful, return the list of entries
        if response.status_code == 200:
            return response.json().get('items', [])
        else:
            # Log and return an empty list in case of errors
            print(f"Error fetching entries from {url}: {response.status_code}")
            return []
    except RequestException as e:
        # Log the exception
        print(f"Failed to fetch entries from {node.id}: {str(e)}")
        return []
    
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