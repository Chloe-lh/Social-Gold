import requests
from django.utils import timezone
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox
from golden.services import get_or_create_foreign_author
from urllib.parse import urljoin
from django.conf import settings
from django.utils.dateparse import parse_datetime
import uuid
import json
from bs4 import BeautifulSoup

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

def normalize_fqid(fqid: str) -> str:
    """Normalize FQID by removing trailing slashes and ensuring consistent format."""
    if not fqid:
        return ""
    return str(fqid).rstrip("/")


def send_activity_to_inbox(recipient: Author, activity: dict):
    """
    Deliver activity to a single recipient's inbox.
    Local recipients → DB inbox insert
    Remote recipients → POST to remote inbox endpoint
    """
    import logging
    logger = logging.getLogger(__name__)

    # LOCAL DELIVERY
    if recipient.host.rstrip("/") == settings.SITE_URL.rstrip("/"):
        Inbox.objects.create(author=recipient, data=activity)
        logger.info(f"Local delivery to {recipient.username}")
        return

    # REMOTE DELIVERY
    # Extract author UUID from recipient.id
    # Handle cases where recipient.id might be:
    # - https://remote-author.com/api/authors/12345/ (correct format)
    # - https://remote-author.com/api/authors/12345/inbox/ (incorrect but possible)
    recipient_id = str(recipient.id).rstrip("/")
    
    # Remove /inbox/ suffix if present
    if recipient_id.endswith("/inbox"):
        recipient_id = recipient_id[:-6]  # Remove "/inbox"
    
    # Extract the author UUID (last segment after /api/authors/)
    if "/api/authors/" in recipient_id:
        author_uuid = recipient_id.split("/api/authors/")[-1].split("/")[0]
    else:
        # Fallback: just get the last segment
        author_uuid = recipient_id.split("/")[-1]
    
    inbox_url = urljoin(recipient.host.rstrip('/') + '/', f"api/authors/{author_uuid}/inbox/")

    try:
        auth = None
        node = Node.objects.filter(id__icontains=recipient.host).first()
        if node and node.auth_user and node.auth_pass:
            auth = (node.auth_user, node.auth_pass)

        logger.info(f"Sending activity to {inbox_url} for recipient {recipient.id}")
        response = requests.post(
            inbox_url,
            data=json.dumps(activity),
            headers={
                "Content-Type": "application/json",
            },
            auth=auth,
            timeout=10,
        )
        
        logger.info(f"Response from {inbox_url}: {response.status_code}")
        
        if response.status_code >= 400:
            logger.error(f"Failed remote inbox delivery to {inbox_url}: {response.status_code} - {response.text[:200]}")
        else:
            logger.info(f"Successfully delivered activity to {inbox_url}")
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout delivering to {inbox_url}")
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error delivering to {inbox_url}")
    except Exception as e:
        logger.exception(f"Exception during remote inbox delivery to {inbox_url}: {e}")


def get_followers(author: Author):
    """Return all authors who follow this author (FOLLOW.state=ACCEPTED)."""
    return Author.objects.filter(
        outgoing_follow_requests__object=author.id, 
        outgoing_follow_requests__state="ACCEPTED"
    )


def get_friends(author):
    """Mutual followers = friends."""
    follower_ids = set(Follow.objects.filter(object=author.id, state="ACCEPTED").values_list("actor_id", flat=True))
    following_ids = set(Follow.objects.filter(actor=author, state="ACCEPTED").values_list("object", flat=True))
    mutual = follower_ids.intersection(following_ids)
    return Author.objects.filter(id__in=mutual)


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
        if src and not src.startswith("http"):
            img["src"] = urljoin(base_url.rstrip("/") + "/", src.lstrip("/"))

    return str(soup)


# * ============================================================
# * Main Distributor
# * ============================================================
def distribute_activity(activity: dict, actor: Author):
    """
    Main distribution function - determines recipients and sends activities.
    """
    import logging
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

    # COMMENT
    if type_lower == "comment" and isinstance(obj, dict):
        entry_author_id = obj.get("entry")
        entry_author = Author.objects.filter(id=entry_author_id).first()
        if not entry_author:
            return

        recipients = {entry_author}
        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # LIKE
    if type_lower == "like":
        liked_fqid = obj if isinstance(obj, str) else None
        if not liked_fqid:
            return

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

    # UNLIKE
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
        target = Author.objects.filter(id=target_id).first()
        
        # If target doesn't exist locally, create stub
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
            target = Author.objects.filter(id=follower_id).first()
            
            # If follower doesn't exist locally, create stub
            if not target and follower_id:
                target = get_or_create_foreign_author(follower_id)
        elif isinstance(follow_obj, str):
            # If it's a Follow ID string, look it up
            follow = Follow.objects.filter(id=follow_obj).first()
            if follow:
                target = follow.actor
                # If actor doesn't exist (shouldn't happen, but be safe)
                if not target:
                    target = get_or_create_foreign_author(follow.actor.id if hasattr(follow, 'actor') else follow.actor_id)
            else:
                # Follow not found locally - might be a remote Follow ID
                # Try to extract author ID from the Follow ID URL pattern
                # This is a fallback for remote Follow IDs we haven't synced
                logger.warning(f"Follow object not found for ID: {follow_obj}")
                target = None
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
        target = Author.objects.filter(id=target_id).first()

        if target:
            send_activity_to_inbox(target, activity)
        return

    # REMOVE FRIEND
    if type_lower == "removefriend":
        target_id = obj
        target = Author.objects.filter(id=target_id).first()

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
    logger.info(f"Processing {inbox_items.count()} inbox items for {author.username}")

    for item in inbox_items:
        activity = item.data
        activity_type = activity.get("type", "").lower()
        obj = activity.get("object")

        logger.info(f"Processing activity: type={activity_type}, id={activity.get('id')}")

        actor_id = activity.get("actor")
        actor = Author.objects.filter(id=actor_id).first()
        if not actor and actor_id:
            actor = get_or_create_foreign_author(actor_id)

        # FOLLOW REQUEST
        if activity_type == "follow":
            follower = actor
            target_id = obj

            if follower and target_id:
                # Delete any existing follow request
                Follow.objects.filter(actor=follower, object=target_id).delete()

                # Create new follow request
                Follow.objects.create(
                    id=activity.get("id"),
                    actor=follower,
                    object=target_id,
                    state="REQUESTED",
                    summary=activity.get("summary", ""),
                    published=parse_datetime(activity.get("published")) or timezone.now()
                )
                logger.info(f"Created follow request: {follower.username} -> {target_id}")

        # ACCEPT FOLLOW
        elif activity_type == "accept":
            follow_obj = obj or {}
            processed = False
            
            # Try to handle as Follow ID string first
            if isinstance(follow_obj, str):
                follow = Follow.objects.filter(id=follow_obj).first()
                if follow:
                    follow.state = "ACCEPTED"
                    follow.published = parse_datetime(activity.get("published")) or timezone.now()
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
                            follow.published = parse_datetime(activity.get("published")) or timezone.now()
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
                                published=parse_datetime(activity.get("published")) or timezone.now()
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
                    follow.published = parse_datetime(activity.get("published")) or timezone.now()
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
                        follow.published = parse_datetime(activity.get("published")) or timezone.now()
                        follow.save()
                    else:
                        Follow.objects.create(
                            id=activity.get("id") or f"{follower.id}/follow/{uuid.uuid4()}",
                            actor=follower,
                            object=target_id,
                            state="REJECTED",
                            summary=activity.get("summary", ""),
                            published=parse_datetime(activity.get("published")) or timezone.now()
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

            Entry.objects.update_or_create(
                id=entry_id,
                defaults={
                    "title": obj.get("title", ""),
                    "content": content,
                    "contentType": obj.get("contentType", "text/plain"),
                    "author": actor or author,
                    "visibility": obj.get("visibility", "PUBLIC"),
                    "published": parse_datetime(obj.get("published")) or timezone.now(),
                }
            )
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

        # COMMENT
        elif activity_type == "comment" and isinstance(obj, dict):
            comment_id = obj.get("id")
            entry = Entry.objects.filter(id=obj.get("entry")).first()

            if entry:
                Comment.objects.update_or_create(
                    id=comment_id,
                    defaults={
                        "entry": entry,
                        "author": Author.objects.filter(id=obj.get("author")).first() or actor,
                        "content": obj.get("content", ""),
                        "contentType": obj.get("contentType", "text/plain"),
                        "published": parse_datetime(obj.get("published")) or timezone.now()
                    }
                )
                logger.info(f"Created comment: {comment_id}")

        # DELETE COMMENT
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "comment":
            Comment.objects.filter(id=obj.get("id")).delete()
            logger.info(f"Deleted comment: {obj.get('id')}")

        # LIKE
        elif activity_type == "like":
            obj_id = activity.get("object")

            Like.objects.filter(author=actor, object=obj_id).delete()
            Like.objects.create(
                id=activity.get("id"),
                author=actor,
                object=obj_id,
                published=parse_datetime(activity.get("published")) or timezone.now()
            )
            logger.info(f"Created like: {actor.username} liked {obj_id}")

        # UNLIKE
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "like":
            Like.objects.filter(author=obj.get("actor"), object=obj.get("object")).delete()
            logger.info(f"Deleted like: {obj.get('actor')} unliked {obj.get('object')}")

        # Mark as processed
        item.processed = True
        item.save()