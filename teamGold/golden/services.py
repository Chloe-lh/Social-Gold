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

def normalize_fqid(fqid: str) -> str:
    """Normalize FQID by removing trailing slashes and ensuring consistent format."""
    return fqid.rstrip("/").lower()  # Ensure lowercase and consistent format

def is_local(author_id):
    author = Author.objects.filter(id=author_id).first()
    return author is not None and author.host == settings.SITE_URL

def get_or_create_author(fqid: str) -> Author:
    """
    Fetch or create a remote or local author.
    If the author is not found locally, we attempt to create a stub for the remote author.
    """
    fqid = normalize_fqid(fqid)
    author, created = Author.objects.get_or_create(id=fqid)
    return author

def create_activity(author, activity_type, object_data, suffix="posts"):
    activity_id = f"{author.id.rstrip('/')}/{suffix}/{uuid.uuid4()}"
    activity = {
        "type": activity_type,
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} performed a {activity_type} activity",
        "object": object_data
    }
    return activity

def create_follow_activity(author, target):
    object_data = {
        "type": "Follow",
        "actor": str(author.id),
        "object": str(target.id),
        "published": timezone.now().isoformat(),
        "state": "REQUESTED"
    }
    return create_activity(author, "Follow", object_data, "follow")

def process_remote_activity(activity_data):
    activity_type = activity_data.get("type", "").lower()
    actor_url = activity_data.get("actor")
    object_url = activity_data.get("object")

    actor = get_or_create_author(actor_url)
    object_author = get_or_create_author(object_url)

    # Process different activity types
    if activity_type == "follow":
        process_follow_activity(actor, object_author)
    elif activity_type == "accept":
        process_accept_activity(actor, object_author)
    elif activity_type == "reject":
        process_reject_activity(actor, object_author)
    
    return True

def process_follow_activity(actor, target):
    follow, created = Follow.objects.get_or_create(actor=actor, object=target)
    follow.state = "REQUESTED"
    follow.save()

def get_remote_node_from_fqid(fqid):
    """
    Extract the remote node from an FQID. This method checks if the FQID is local or remote.
    If remote, it attempts to resolve the remote node using the provided FQID.
    """
    if is_local(fqid):
        return None  
    fqid = normalize_fqid(fqid)
    node = Node.objects.filter(id__startswith=urlparse(fqid).netloc).first()
    
    if node and node.is_active:
        return node
    return None









# ! OLD ASS CODE !

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

def fqid_to_uuid(fqid: str) -> str:
    """Convert a full FQID to UUID, ensuring correct extraction."""
    fqid = fqid.rstrip("/")
    return fqid.split("/")[-1]

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
        raw_content = remote_entry.get('content', '')
        author_data = remote_entry.get('author', {})
        author_id = author_data.get('id')
        
        # Get or create the author
        author = Author.objects.filter(id=author_id).first()
        if not author:
            author = get_or_create_foreign_author(author_id)
        
        if not author:
            print(f"Error syncing remote entry: Could not get or create author {author_id}")
            return None

        # Absolutize image URLs in content (convert relative to absolute)
        from .distributor import absolutize_remote_images
        base_url = node.id.rstrip('/')
        content = absolutize_remote_images(raw_content, base_url)

        # Create or update the entry
        entry, created = Entry.objects.update_or_create(
            id=entry_id,
            defaults={
                'author': author,
                'title': title,
                'content': content,
                'contentType': remote_entry.get('contentType', 'text/plain'),
                'visibility': remote_entry.get('visibility', 'PUBLIC'),
                'published': remote_entry.get('published'),
            }
        )
        
        return entry
    except Exception as e:
        print(f"Error syncing remote entry: {e}")
        import traceback
        traceback.print_exc()
        return None
    
def fetch_remote_entries(node, timeout=5):
    """
    Fetch entries from a remote node's API.

    :param node: The Node instance representing the remote server.
    :param timeout: Timeout duration for the HTTP request.
    :return: A list of remote entries (parsed JSON response).
    """
    try:
        url = f"{node.id.rstrip('/')}/api/entries/"
        response = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        if response.status_code == 200:
            return response.json().get("items", [])
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching entries from {url}: {e}")
    return []

def fetch_or_create_author(author_url):
    """
    Fetch or create a remote author by their URL.
    """
    from golden.models import Author

    # Check if author already exists locally
    author = Author.objects.filter(id=author_url).first()

    if not author:
        # If the author doesn't exist, fetch their data from the remote node and create a new author entry
        author_data = fetch_remote_author_data(author_url)
        if author_data:
            author = Author.objects.create(
                id=author_url,
                username=author_data.get("username"),
                host=author_data.get("host"),
                profileImage=author_data.get("profileImage"),
                # Other fields as needed
            )
    return author

def fetch_remote_author_data(author_url):
    """
    Fetch remote author data from the given URL (using ActivityPub or other protocols).
    """
    try:
        response = requests.get(f"{author_url}/api/authors/")
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching remote author data: {e}")
    return None

def get_or_create_foreign_author(remote_id: str, host: str = None, username: str = None) -> Author:
    """
    Ensure we can create or retrieve an author from a remote node.

    Accepts an optional `host` parameter (used by callers that already
    know the host) to avoid parsing or unnecessary network calls.
    Accepts an optional `username` parameter to set the username when creating.
    """
    remote_id = normalize_fqid(remote_id)
    
    # Check if author already exists by FQID
    author = Author.objects.filter(id=remote_id).first()
    if author:
        # If username was provided and differs, update it
        if username and author.username != username:
            author.username = username
            author.save(update_fields=['username'])
        return author
    
    # Also check by username if username is provided (to avoid duplicates)
    if username:
        existing = Author.objects.filter(username=username, host=host or urlparse(remote_id).netloc).first()
        if existing:
            # Update the ID if it's different
            if existing.id != remote_id:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Found author '{username}' with different ID: {existing.id} vs {remote_id}")
            return existing
    
    # Check if remote_id is a full URL or just a UUID
    host_val = host
    if not host_val:
        if "/api/authors/" in remote_id or remote_id.startswith("http"):
            parsed = urlparse(remote_id)
            host_val = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
        else:
            # If it's just a UUID and no host provided, we can't create a proper FQID
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Cannot create foreign author from UUID without host: {remote_id}")
            return None
    
    # If remote_id is just a UUID, reconstruct the full FQID
    if not "/api/authors/" in remote_id and not remote_id.startswith("http"):
        uuid_part = remote_id.rstrip("/")
        remote_id = f"{host_val}/api/authors/{uuid_part}"
    
    guessed_username = username or remote_id.split("/")[-1] if "/" in remote_id else remote_id
    
    author, created = Author.objects.get_or_create(
        id=remote_id,  # Store remote author ID as FQID
        defaults={
            'username': guessed_username,
            'host': host_val,
            'is_approved': True,
        }
    )
    
    # Update username if provided and different
    if username and author.username != username:
        author.username = username
        author.save(update_fields=['username'])
    
    return author
    
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