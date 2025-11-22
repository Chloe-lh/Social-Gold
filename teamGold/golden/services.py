# golden/services.py
from django.db import transaction
from .models import Author
from .utils import is_local 
import logging
from datetime import timezone
from urllib.parse import unquote, urlparse
import uuid

def normalize_fqid(fqid: str) -> str:
    if not fqid:
        return ""
    return str(fqid).rstrip("/")

def is_local(fqid: str) -> bool:
    author_host = urlparse(fqid).netloc
    site_host = urlparse(settings.SITE_URL).netloc
    return author_host == site_host

def get_or_create_author(fqid: str) -> Author:
    """
    Fetch or create a local author using their username. If not found by username,
    fall back to using FQID.
    """
    # Normalize the FQID to ensure it's in the correct format
    fqid = normalize_fqid(fqid)
    
    # Extract the username from FQID
    username = fqid.split("/")[-1]  # Assuming the username is at the end of the FQID path
    
    # Try to get the author using the username
    author = Author.objects.filter(username=username).first()
    
    # If author doesn't exist by username, fall back to FQID
    if not author:
        author, created = Author.objects.get_or_create(id=fqid)
    
    return author

def get_or_create_foreign_author(remote_id: str) -> Author:
    """
    This function ensures that we can create or retrieve a foreign author based on username.
    If not found by username, fallback to FQID.
    """
    remote_id = normalize_fqid(remote_id)
    
    # Extract the username from the remote_id (FQID)
    username = remote_id.split("/")[-1]  # Assuming username is at the end of the FQID
    
    # Try to get the author by username
    author = Author.objects.filter(username=username).first()
    
    if not author:
        # If not found by username, create or fetch the author by FQID
        author, created = Author.objects.get_or_create(
            id=remote_id, 
            defaults={'username': username}
        )
    
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
    """
    Process the 'follow' activity and create a follow relationship based on username.
    """
    # Ensure target is found by username
    target = get_or_create_author(target.id)
    
    if actor.username == target.username:
        return  # Don't follow yourself
    
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