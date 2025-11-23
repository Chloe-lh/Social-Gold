import requests
from django.utils import timezone
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox
from golden.services import get_or_create_foreign_author, normalize_fqid
from urllib.parse import urljoin
from django.conf import settings
from django.utils.dateparse import parse_datetime
from datetime import datetime as dt

def safe_parse_datetime(value):
    """
    Safely parse a datetime value that could be:
    - A string (ISO format)
    - A datetime object
    - None
    - Some other type
    Returns a datetime object or None.
    """
    if value is None:
        return None
    
    # If it's already a datetime object, return it
    if isinstance(value, dt):
        return value
    
    # If it's a string, try to parse it
    if isinstance(value, str):
        # Try parse_datetime first (handles ISO format)
        parsed = parse_datetime(value)
        if parsed:
            return parsed
        # If that fails, try fromisoformat (Python 3.7+)
        try:
            # Handle 'Z' timezone indicator and various formats
            value_clean = value.replace('Z', '+00:00')
            return dt.fromisoformat(value_clean)
        except (ValueError, AttributeError):
            pass
    
    # If we can't parse it, return None
    return None
import uuid
import json
from bs4 import BeautifulSoup
import logging

"""
This module connects our views and remote nodes with our local database using
an ActivityPub-style architecture. This approach prevents direct relationships and 
content manipulation using our database. Through this inbox method, we can send and
receive deliveries and update our database through this protocol. 

    Step #1: Views create activity dicts and call distribute_activity(activity, actor)

    Step #2: distribute_activity(activity, actor) will decide who should receive that call 
    based on its type and visibility. Afterwards, it will call send_activity() for each recipient 
    that needs that activity. 

    Step #3: send_activity() delivers the activity via an inbox model
        * if it's a local author, then our inbox model
        * if it's a remote author, then through the remote node's inbox URL using the HTTP POST Method. 

    Step #4: process_inbox(author) will then run on the receiving side, reading all unprocessed Inbox rows
    for that author and updated the local database as needed. Afterwards, it will mark the item in the Inbox 
    as processed so that it can be archived. 
"""

# * ============================================================
# * Distributor Helper Functions
# * ============================================================
# Note: normalize_fqid is imported from golden.services to ensure consistency


def send_activity_to_inbox(recipient: Author, activity: dict):
    """Send activity to local or remote inbox."""
    if recipient.host.rstrip("/") == settings.SITE_URL.rstrip("/"):
        # Local delivery to the inbox
        Inbox.objects.create(author=recipient, data=activity)
        return

    # For remote inbox, construct the URL properly
    # The inbox endpoint expects: /api/authors/<author_id>/inbox/
    # Extract the UUID or author ID part from the full FQID
    recipient_id = str(recipient.id).rstrip('/')
    
    # Extract the author ID part (UUID) from the FQID
    # FQID format: https://node.com/api/authors/{uuid}
    if '/api/authors/' in recipient_id:
        author_id_part = recipient_id.split('/api/authors/')[-1]
    else:
        # Fallback: use the last part of the URL
        author_id_part = recipient_id.split('/')[-1]
    
    # Construct inbox URL: host/api/authors/{uuid}/inbox/
    inbox_url = f"{recipient.host.rstrip('/')}/api/authors/{author_id_part}/inbox/"

    # Get node authentication if available
    from .models import Node
    from urllib.parse import urlparse
    parsed = urlparse(recipient.host)
    node_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    node = Node.objects.filter(id__startswith=node_base).first()
    auth = None
    if node and node.auth_user:
        auth = (node.auth_user, node.auth_pass)
        logging.info(f"Using auth for node {node.id}: user={node.auth_user}")
    
    try:
        # Ensure all datetime values are strings before JSON serialization
        def ensure_datetime_strings(obj):
            """Recursively convert datetime objects to ISO format strings"""
            if isinstance(obj, dt):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: ensure_datetime_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [ensure_datetime_strings(item) for item in obj]
            return obj
        
        activity_clean = ensure_datetime_strings(activity)
        
        response = requests.post(
            inbox_url,
            data=json.dumps(activity_clean, default=str),  # default=str handles any remaining non-serializable objects
            headers={"Content-Type": "application/json"},
            auth=auth,
            timeout=10,
        )
        if response.status_code >= 400:
            logging.error(f"Failed to send activity to {inbox_url}: HTTP {response.status_code} - {response.text}")
            raise Exception(f"Error {response.status_code}: {response.text}")
        logging.info(f"Successfully sent activity to {inbox_url} (HTTP {response.status_code})")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send activity to {inbox_url}: {e}")
        raise

def get_followers(author: Author):
    """Return all authors who follow this author (FOLLOW.state=ACCEPTED)."""
    # Query Follow objects directly to work with both local and remote authors
    # The object field is a URLField (FQID), so we need to normalize for matching
    from golden.services import normalize_fqid
    author_id_normalized = normalize_fqid(str(author.id))
    follower_ids = Follow.objects.filter(
        object=author_id_normalized,
        state="ACCEPTED"
    ).values_list("actor_id", flat=True)
    
    # Also try with raw author.id in case normalization differs
    if not follower_ids:
        follower_ids = Follow.objects.filter(
            object=str(author.id).rstrip('/'),
            state="ACCEPTED"
        ).values_list("actor_id", flat=True)
    
    return Author.objects.filter(id__in=follower_ids)


def get_friends(author):
    """Mutual followers = friends."""
    # Normalize author ID for consistent matching with Follow objects
    from golden.services import normalize_fqid
    author_id_normalized = normalize_fqid(str(author.id))
    
    # Get followers (people who follow this author) - actor_id is ForeignKey to Author
    follower_ids = set(Follow.objects.filter(
        object=author_id_normalized,
        state="ACCEPTED"
    ).values_list("actor_id", flat=True))
    
    # Also try with raw author.id in case normalization differs
    if not follower_ids:
        follower_ids = set(Follow.objects.filter(
            object=str(author.id).rstrip('/'),
            state="ACCEPTED"
        ).values_list("actor_id", flat=True))
    
    # Get following (people this author follows) - object is URLField (FQID string)
    following_ids = set(Follow.objects.filter(
        actor=author,
        state="ACCEPTED"
    ).values_list("object", flat=True))
    
    # Normalize following_ids for comparison
    following_ids_normalized = {normalize_fqid(str(fid)) for fid in following_ids}
    
    # Find mutual: authors whose ID (normalized) appears in both sets
    # follower_ids contains Author.id values (from ForeignKey)
    # following_ids_normalized contains normalized FQID strings
    mutual_author_ids = []
    for follower_id in follower_ids:
        # follower_id is an Author.id (URLField), normalize it for comparison
        follower_id_normalized = normalize_fqid(str(follower_id))
        if follower_id_normalized in following_ids_normalized:
            mutual_author_ids.append(follower_id)
    
    # Return Author objects for mutual friends
    if mutual_author_ids:
        return Author.objects.filter(id__in=mutual_author_ids)
    
    return Author.objects.none()


def previously_delivered(post):
    """Return all authors who already received this post."""
    inbox_rows = Inbox.objects.filter(data__object__id=str(post.id))
    author_ids = inbox_rows.values_list("author_id", flat=True)
    return Author.objects.filter(id__in=author_ids)


def absolutize_remote_images(html, base_url):
    """
    If a src is relative (e.g. /media/x.jpg), it is converted to
    base_url + that path (e.g. https://remote-node.com/media/x.jpg).
    """
    if not html or not base_url:
        return html
    
    soup = BeautifulSoup(html, "html.parser")

    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            # Convert relative URLs (starting with /) to absolute URLs
            if src.startswith("/"):
                img["src"] = urljoin(base_url.rstrip("/") + "/", src.lstrip("/"))
            # Also handle relative URLs without leading slash (but skip data: URLs and already absolute URLs)
            elif not src.startswith("http") and not src.startswith("data:"):
                img["src"] = urljoin(base_url.rstrip("/") + "/", src)

    return str(soup)


# * ============================================================
# * Main Distributor
# * ============================================================
def distribute_activity(activity: dict, actor: Author):
    """
    Main distribution function - determines recipients and sends activities.
    It prioritizes FQID for author comparisons and activities.
    """
    logger = logging.getLogger(__name__)

    type_lower = activity.get("type", "").lower()
    obj = activity.get("object")

    logger.info(f"Distributing activity: type={type_lower}, actor={actor.username}")

    # CREATE ENTRY
    if type_lower == "create" and isinstance(obj, dict) and obj.get("type") == "post":
        visibility = obj.get("visibility", "PUBLIC").upper()

        if visibility == "PUBLIC":
            recipients = set(get_followers(actor)) | set(get_friends(actor))
        elif visibility == "UNLISTED":
            recipients = set(get_followers(actor))
        elif visibility == "FRIENDS":
            recipients = set(get_friends(actor))
        else:
            recipients = set()

        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # UPDATE ENTRY
    if type_lower == "update" and isinstance(obj, dict) and obj.get("type") == "post":
        visibility = obj.get("visibility", "PUBLIC").upper()
        recipients = set()

        if visibility == "PUBLIC":
            recipients |= set(get_followers(actor))
            recipients |= set(get_friends(actor))
        elif visibility == "UNLISTED":
            recipients |= set(get_followers(actor))
        elif visibility == "FRIENDS":
            recipients |= set(get_friends(actor))

        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # DELETE ENTRY
    if type_lower == "delete" and isinstance(obj, dict) and obj.get("type") == "post":
        recipients = set(get_followers(actor)) | set(get_friends(actor))
        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # COMMENT - handle both deepskyblue spec format and ActivityPub format
    if type_lower == "comment":
        # deepskyblue spec: object is entry FQID string, comment content is in "comment" field
        entry_id = None
        if isinstance(obj, str):
            # deepskyblue format: object is entry FQID
            entry_id = obj
        elif isinstance(obj, dict):
            # ActivityPub format: object is dict with entry field
            entry_id = obj.get("entry")
        
        if not entry_id:
            logger.warning(f"Comment activity missing entry ID: {activity}")
            return
        
        # Get the entry to find its author
        entry = Entry.objects.filter(id=normalize_fqid(entry_id)).first()
        if not entry:
            # Try without normalization
            entry = Entry.objects.filter(id=entry_id).first()
        
        # If entry not found locally, try to extract author FQID from entry FQID or fetch entry
        if not entry:
            logger.info(f"Entry not found locally for comment distribution: entry_id={entry_id}, attempting to sync or extract author")
            # Try to sync the entry from remote node
            from golden.services import sync_remote_entry
            entry = sync_remote_entry(entry_id)
        
        if entry:
            recipients = {entry.author}
            for r in recipients:
                send_activity_to_inbox(r, activity)
        else:
            # Last resort: try to extract author from entry FQID pattern
            # Entry FQID format: https://node.com/api/authors/{author_uuid}/entries/{entry_uuid}
            # Or: https://node.com/api/entries/{entry_uuid} (need to fetch to get author)
            logger.warning(f"Could not find entry or extract author for comment: entry_id={entry_id}")
        return

    # LIKE
    if type_lower == "like":
        liked_fqid = obj if isinstance(obj, str) else None
        if not liked_fqid:
            return

        # Try to find entry locally (with normalization)
        entry = Entry.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not entry:
            entry = Entry.objects.filter(id=liked_fqid).first()
        
        # Try to find comment locally
        comment = Comment.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not comment:
            comment = Comment.objects.filter(id=liked_fqid).first()

        recipients = set()
        
        if entry:
            recipients.add(entry.author)
        elif comment:
            recipients.add(comment.author)
        else:
            # Entry/comment not found locally - try to sync from remote
            logger.info(f"Entry/comment not found locally for like distribution: liked_fqid={liked_fqid}, attempting to sync")
            from golden.services import sync_remote_entry
            entry = sync_remote_entry(liked_fqid)
            if entry:
                recipients.add(entry.author)
            else:
                # Try to extract author from FQID pattern
                # Entry FQID: https://node.com/api/authors/{author_uuid}/entries/{entry_uuid}
                if '/api/authors/' in liked_fqid and '/entries/' in liked_fqid:
                    # Extract author FQID from entry FQID
                    author_fqid = '/api/authors/'.join(liked_fqid.split('/api/authors/')[:2]).split('/entries/')[0]
                    author = get_or_create_foreign_author(author_fqid)
                    if author:
                        recipients.add(author)
                        logger.info(f"Extracted author from entry FQID: {author_fqid}")
                else:
                    logger.warning(f"Could not find entry/comment or extract author for like: liked_fqid={liked_fqid}")

        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # UNLIKE - handle both "unlike" (deepskyblue spec) and "undo" (ActivityPub) formats
    if type_lower == "unlike":
        # deepskyblue spec format: object is directly the FQID string
        liked_fqid = obj if isinstance(obj, str) else None
        if not liked_fqid:
            return

        # Try to find entry locally (with normalization)
        entry = Entry.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not entry:
            entry = Entry.objects.filter(id=liked_fqid).first()
        
        # Try to find comment locally
        comment = Comment.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not comment:
            comment = Comment.objects.filter(id=liked_fqid).first()

        recipients = set()
        
        if entry:
            recipients.add(entry.author)
        elif comment:
            recipients.add(comment.author)
        else:
            # Entry/comment not found locally - try to sync from remote
            logger.info(f"Entry/comment not found locally for unlike distribution: liked_fqid={liked_fqid}, attempting to sync")
            from golden.services import sync_remote_entry
            entry = sync_remote_entry(liked_fqid)
            if entry:
                recipients.add(entry.author)
            else:
                # Try to extract author from FQID pattern
                if '/api/authors/' in liked_fqid and '/entries/' in liked_fqid:
                    author_fqid = '/api/authors/'.join(liked_fqid.split('/api/authors/')[:2]).split('/entries/')[0]
                    author = get_or_create_foreign_author(author_fqid)
                    if author:
                        recipients.add(author)
                        logger.info(f"Extracted author from entry FQID: {author_fqid}")
                else:
                    logger.warning(f"Could not find entry/comment or extract author for unlike: liked_fqid={liked_fqid}")

        for r in recipients:
            send_activity_to_inbox(r, activity)
        return
    
    # UNLIKE (ActivityPub format - keep for backward compatibility)
    if type_lower == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "like":
        liked_fqid = obj.get("object")
        entry = Entry.objects.filter(id=liked_fqid).first()
        comment = Comment.objects.filter(id=liked_fqid).first()

        if entry:
            recipients = {entry.author}
        elif comment:
            recipients = {comment.author}
        else:
            return

        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # FOLLOW
    if type_lower == "follow":
        target_id = obj
        target = Author.objects.filter(id=normalize_fqid(target_id)).first()

        # If target doesn't exist locally by FQID, create stub
        if not target:
            target = get_or_create_foreign_author(target_id)
        
        if target:
            send_activity_to_inbox(target, activity)
        return

    # ACCEPT or REJECT
    if type_lower == "accept" or type_lower == "reject":
        follow_obj = obj or {}

        if isinstance(follow_obj, dict):
            follower_id = follow_obj.get("actor")  # Who made the follow request
            target = Author.objects.filter(id=normalize_fqid(follow_obj.get("object"))).first()

            if not target and follower_id:
                target = get_or_create_foreign_author(follower_id)
        elif isinstance(follow_obj, str):
            # If it's a Follow ID string, look it up
            follow = Follow.objects.filter(id=follow_obj).first()
            if follow:
                target = follow.actor
                # If actor doesn't exist (shouldn't happen, but be safe)
                if not target:
                    target = get_or_create_foreign_author(follow.actor.username if hasattr(follow, 'actor') else follow.actor_id)
            else:
                target = None
        
        if target:
            send_activity_to_inbox(target, activity)
            logger.info(f"Sent {type_lower} activity to {target.username or target.id}")
        else:
            logger.warning(f"Could not determine target for {type_lower} activity: {obj}")
        return

    # UNFOLLOW
    if type_lower == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "follow":
        target_id = obj.get("object")
        target = Author.objects.filter(id=normalize_fqid(target_id)).first()

        if target:
            send_activity_to_inbox(target, activity)
        return

    # REMOVE FRIEND
    if type_lower == "removefriend":
        target_id = obj
        target = Author.objects.filter(id=normalize_fqid(target_id)).first()

        if target:
            send_activity_to_inbox(target, activity)
        return

# * ============================================================
# * Inbox Processor
# * ============================================================

def process_inbox(author: Author):
    """
    Process all unprocessed inbox items for an author.
    """
    import logging
    logger = logging.getLogger(__name__)

    inbox_items = Inbox.objects.filter(author=author, processed=False)

    for item in inbox_items:
        activity = item.data
        activity_type = activity.get("type", "").lower()
        obj = activity.get("object")

        # Handle actor - can be either a string (FQID) or a dict (author object)
        actor_data = activity.get("actor")
        actor_id = None
        actor_username = None
        actor_host = None
        
        if isinstance(actor_data, dict):
            # Actor is a full object with username, host, etc.
            actor_id = actor_data.get("id") or actor_data.get("@id")
            actor_username = actor_data.get("username") or actor_data.get("displayName")
            actor_host = actor_data.get("host")
        elif isinstance(actor_data, str):
            # Actor is just an FQID string
            actor_id = actor_data
        
        actor = None
        if actor_id:
            actor = Author.objects.filter(id=normalize_fqid(actor_id)).first()
            if not actor:
                # Create foreign author with username if available
                actor = get_or_create_foreign_author(
                    actor_id,
                    host=actor_host,
                    username=actor_username
                )

        # FOLLOW REQUEST
        if activity_type == "follow":
            follower = actor
            target_id = normalize_fqid(obj)
            
            # Debug: Log what we're creating
            logger.info(f"[process_inbox] Processing Follow activity from {follower.username if follower else 'Unknown'} (id: {actor_id})")
            logger.info(f"[process_inbox] Follow activity object (raw): '{obj}'")
            logger.info(f"[process_inbox] Follow activity object (normalized): '{target_id}'")
            logger.info(f"[process_inbox] Inbox author (who is being followed): {author.username} (id: {author.id})")

            if follower and target_id:
                # Verify target_id matches the inbox author (person being followed)
                author_id_normalized = normalize_fqid(str(author.id))
                if target_id != author_id_normalized:
                    logger.warning(f"[process_inbox] WARNING: target_id '{target_id}' doesn't match inbox author ID '{author_id_normalized}'")
                    logger.warning(f"[process_inbox] Using inbox author ID instead for Follow object")
                    target_id = author_id_normalized
                
                # Delete any existing follow request
                Follow.objects.filter(actor=follower, object=target_id).delete()

                follow_obj = Follow.objects.create(
                    id=activity.get("id"),
                    actor=follower,
                    object=target_id,
                    state="REQUESTED",
                    summary=activity.get("summary", ""),
                    published=safe_parse_datetime(activity.get("published")) or timezone.now()
                )
                # Mark inbox item as processed
                item.processed = True
                item.save()
                logger.info(f"[process_inbox] Created follow request: {follower.username if follower else 'Unknown'} -> {target_id}")
                logger.info(f"[process_inbox] Follow object created: actor={follow_obj.actor.id}, object={follow_obj.object}, state={follow_obj.state}")
                logger.info(f"[process_inbox] Marked inbox item {item.id} as processed")

        # ACCEPT FOLLOW
        elif activity_type == "accept":
            follow_obj = obj or {}
            processed = False
            
            # Try to handle as Follow ID string first
            if isinstance(follow_obj, str):
                follow = Follow.objects.filter(id=follow_obj).first()
                if follow:
                    follow.state = "ACCEPTED"
                    follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                    follow.save()
                    
                    follower = follow.actor
                    target = Author.objects.filter(id=follow.object).first()
                    if follower and target:
                        follower.following.add(target)
                        logger.info(f"Accepted follow: {follower.username} now follows {target.username}")
                        processed = True
            
            # If not processed yet, handle as dict object structure (actor/object pair)
            if not processed and isinstance(follow_obj, dict):
                follower_id = follow_obj.get("actor")
                target_id = follow_obj.get("object")

                if follower_id and target_id:
                    follower = Author.objects.filter(id=follower_id).first()
                    if not follower:
                        follower = get_or_create_foreign_author(follower_id)
                    
                    target = Author.objects.filter(id=target_id).first()
                    if not target:
                        target = get_or_create_foreign_author(target_id)

                    if follower and target:
                        # Look up existing Follow object by actor/object pair
                        follow = Follow.objects.filter(actor=follower, object=target_id).first()
                        if follow:
                            follow.state = "ACCEPTED"
                            follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                            follow.save()
                        else:
                            # Create new Follow object in ACCEPTED state
                            # Try to use the Follow ID from the Accept activity's object if it was a string
                            follow_id = activity.get("object") if isinstance(activity.get("object"), str) else None
                            if not follow_id:
                                follow_id = f"{follower.id}/follow/{uuid.uuid4()}"
                            
                            Follow.objects.create(
                                id=follow_id,
                                actor=follower,
                                object=target_id,
                                state="ACCEPTED",
                                summary=activity.get("summary", ""),
                                published=safe_parse_datetime(activity.get("published")) or timezone.now()
                            )
                        
                        follower.following.add(target)
                        logger.info(f"Accepted follow: {follower.username if follower else follower_id} now follows {target.username if target else target_id}")
                        processed = True
            
            if not processed:
                logger.warning(f"Unable to process Accept activity: follow_obj={follow_obj}, activity_id={activity.get('id')}")

        # REJECT FOLLOW
        elif activity_type == "reject":
            follow_obj = obj or {}
            
            if isinstance(follow_obj, str):
                follow = Follow.objects.filter(id=follow_obj).first()
                if follow:
                    follow.state = "REJECTED"
                    follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                    follow.save()
                    logger.info(f"Rejected follow: {follow.actor.username} -> {follow.object}")
            else:
                follower_id = follow_obj.get("actor")
                target_id = follow_obj.get("object")

                follower = Author.objects.filter(id=follower_id).first()
                target = Author.objects.filter(id=target_id).first()

                if follower and target:
                    follow = Follow.objects.filter(actor=follower, object=target_id).first()
                    if follow:
                        follow.state = "REJECTED"
                        follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                        follow.save()
                    else:
                        Follow.objects.create(
                            id=activity.get("id") or f"{follower.id}/follow/{uuid.uuid4()}",
                            actor=follower,
                            object=target_id,
                            state="REJECTED",
                            summary=activity.get("summary", ""),
                            published=safe_parse_datetime(activity.get("published")) or timezone.now()
                        )
                    logger.info(f"Rejected follow: {follower.username} -> {target.username}")

        # UNFOLLOW
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "follow":
            follower_id = obj.get("actor")
            target_id = obj.get("object")

            follower = Author.objects.filter(id=follower_id).first()
            target = Author.objects.filter(id=target_id).first()

            if follower and target:
                Follow.objects.filter(actor=follower, object=target_id).delete()
                follower.following.remove(target)
                logger.info(f"Unfollowed: {follower.username} stopped following {target.username}")

        # REMOVE FRIEND
        elif activity_type == "removefriend":
            target_id = obj
            target = Author.objects.filter(id=target_id).first()
            initiator = actor

            if initiator and target:
                initiator.following.remove(target)
                target.following.remove(initiator)
                Follow.objects.filter(actor=initiator, object=target_id).delete()
                Follow.objects.filter(actor=target, object=initiator.id).delete()
                logger.info(f"Removed friend: {initiator.username} <-> {target.username}")

        # CREATE ENTRY
        elif activity_type == "create" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")

            raw_content = obj.get("content", "") or ""
            base_url = getattr(actor, "host", "") if actor else ""
            content = absolutize_remote_images(raw_content, base_url)

            entry, created = Entry.objects.update_or_create(
                id=entry_id,
                defaults={
                    "title": obj.get("title", ""),
                    "content": content,
                    "contentType": obj.get("contentType", "text/plain"),
                    "author": actor or author,
                    "visibility": obj.get("visibility", "PUBLIC"),
                    "published": safe_parse_datetime(obj.get("published")) or timezone.now(),
                }
            )
            
            # Process entry images from attachments
            # For remote entries, images are embedded in HTML content and will display there
            # We also store image URLs in entry metadata for the /api/authors/<uuid>/entries/<uuid>/images/ endpoint
            attachments = obj.get("attachments", [])
            if attachments:
                logger.info(f"Entry {entry_id} has {len(attachments)} image attachments")
                # Images are already in HTML content via absolutize_remote_images
                # The images endpoint will extract URLs from attachments or HTML content
            
            logger.info(f"Created entry: {entry_id}")

        # UPDATE ENTRY
        elif activity_type == "update" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")
            entry = Entry.objects.filter(id=entry_id).first()

            if entry:
                raw_content = obj.get("content", entry.content) or entry.content
                base_url = getattr(actor, "host", "") if actor else ""
                content = absolutize_remote_images(raw_content, base_url)

                entry.title = obj.get("title", entry.title)
                entry.content = content
                entry.contentType = obj.get("contentType", entry.contentType)
                entry.visibility = obj.get("visibility", entry.visibility)
                entry.save()
                logger.info(f"Updated entry: {entry_id}")

        # DELETE ENTRY
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")
            entry = Entry.objects.filter(id=entry_id).first()
            if entry:
                entry.visibility = "DELETED"
                entry.save()
                logger.info(f"Deleted entry: {entry_id}")

        # COMMENT - handle both deepskyblue spec format and ActivityPub format
        elif activity_type == "comment":
            # deepskyblue spec format: {"type": "comment", "id": "...", "comment": "...", "author": {...}, "object": "entry_fqid"}
            # ActivityPub format: {"type": "comment", "object": {"type": "comment", "id": "...", "entry": "...", ...}}
            
            comment_id = activity.get("id")  # Comment FQID
            entry_id = None
            comment_content = None
            comment_content_type = None
            comment_author_id = None
            
            if isinstance(obj, str):
                # deepskyblue format: object is entry FQID string
                entry_id = obj
                comment_content = activity.get("comment", "")  # Spec uses "comment" field
                comment_content_type = activity.get("contentType", "text/plain")
                # Author is in activity["author"] as object
                author_data = activity.get("author")
                if isinstance(author_data, dict):
                    comment_author_id = author_data.get("id")
                elif isinstance(author_data, str):
                    comment_author_id = author_data
            elif isinstance(obj, dict):
                # ActivityPub format: object is comment dict
                entry_id = obj.get("entry")
                comment_content = obj.get("content", "")
                comment_content_type = obj.get("contentType", "text/plain")
                comment_author_id = obj.get("author")
                if not comment_id:
                    comment_id = obj.get("id")
            
            if not entry_id:
                logger.warning(f"Comment activity missing entry ID: {activity}")
                return
            
            entry = Entry.objects.filter(id=normalize_fqid(entry_id)).first()
            if not entry:
                entry = Entry.objects.filter(id=entry_id).first()
            
            if entry:
                # Get or create comment author (could be remote)
                comment_author = None
                if comment_author_id:
                    if isinstance(comment_author_id, dict):
                        comment_author_id = comment_author_id.get("id")
                    comment_author = Author.objects.filter(id=normalize_fqid(comment_author_id)).first()
                    if not comment_author:
                        # Extract username from author object if available
                        author_obj = activity.get("author") if isinstance(activity.get("author"), dict) else None
                        username = author_obj.get("username") or author_obj.get("displayName") if author_obj else None
                        host = author_obj.get("host") if author_obj else None
                        comment_author = get_or_create_foreign_author(comment_author_id, host=host, username=username)
                
                if not comment_author:
                    comment_author = actor  # Fallback to inbox actor
                
                if not comment_id:
                    # Generate comment ID if not provided
                    from golden.services import generate_comment_fqid
                    comment_id = generate_comment_fqid(comment_author, entry)
                
                Comment.objects.update_or_create(
                    id=comment_id,
                    defaults={
                        "entry": entry,
                        "author": comment_author,
                        "content": comment_content or "",
                        "contentType": comment_content_type or "text/plain",
                        "published": safe_parse_datetime(activity.get("published")) or timezone.now()
                    }
                )
                logger.info(f"Created/updated comment: {comment_id} on entry {entry_id}")
            else:
                logger.warning(f"Entry not found for comment: entry_id={entry_id}")

        # DELETE COMMENT
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "comment":
            Comment.objects.filter(id=obj.get("id")).delete()
            logger.info(f"Deleted comment: {obj.get('id')}")

        # LIKE
        elif activity_type == "like":
            obj_id = activity.get("object")

            # Delete existing like first (idempotent)
            Like.objects.filter(author=actor, object=obj_id).delete()
            
            # Create new like
            like = Like.objects.create(
                id=activity.get("id"),
                author=actor,
                object=obj_id,
                published=safe_parse_datetime(activity.get("published")) or timezone.now()
            )
            
            # Update entry's likes ManyToMany if it's an entry
            entry = Entry.objects.filter(id=obj_id).first()
            if entry:
                entry.likes.add(actor)
                logger.info(f"Created like: {actor.username} liked entry {obj_id}")
            else:
                logger.info(f"Created like: {actor.username} liked {obj_id}")

        # UNLIKE - handle both "unlike" (deepskyblue spec) and "undo" (ActivityPub) formats
        elif activity_type == "unlike":
            # deepskyblue spec format: object is directly the FQID string
            obj_id = obj if isinstance(obj, str) else None
            actor_id = activity.get("actor")
            
            if not obj_id:
                logger.warning(f"Unlike activity missing object: {activity}")
                return
            
            # Find the actor (could be remote)
            like_actor = Author.objects.filter(id=actor_id).first()
            if not like_actor and actor_id:
                like_actor = get_or_create_foreign_author(actor_id)
            
            if like_actor:
                Like.objects.filter(author=like_actor, object=obj_id).delete()
                
                # Update entry's likes ManyToMany if it's an entry
                entry = Entry.objects.filter(id=obj_id).first()
                if entry:
                    entry.likes.remove(like_actor)
                
                logger.info(f"Deleted like: {like_actor.username if like_actor else actor_id} unliked {obj_id}")
        
        # UNLIKE (ActivityPub format - keep for backward compatibility)
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "like":
            obj_id = obj.get("object")
            actor_id = obj.get("actor")
            
            # Find the actor (could be remote)
            like_actor = Author.objects.filter(id=actor_id).first()
            if not like_actor and actor_id:
                like_actor = get_or_create_foreign_author(actor_id)
            
            if like_actor:
                Like.objects.filter(author=like_actor, object=obj_id).delete()
                
                # Update entry's likes ManyToMany if it's an entry
                entry = Entry.objects.filter(id=obj_id).first()
                if entry:
                    entry.likes.remove(like_actor)
                
                logger.info(f"Deleted like: {like_actor.username if like_actor else actor_id} unliked {obj_id}")

        # Mark as processed after successful processing
        # processed variable is only set for ACCEPT, so check activity_type for others
        if activity_type in ["follow", "accept", "reject", "unlike", "undo", "removefriend", "create", "update", "delete", "comment", "like"]:
            item.processed = True
            item.save()
            logger.info(f"Marked inbox item {item.id} as processed (activity_type={activity_type})")