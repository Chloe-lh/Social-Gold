import requests
from django.utils import timezone
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox
from golden.services import is_local
from urllib.parse import urljoin
from django.conf import settings
from django.utils.dateparse import parse_datetime
import uuid

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

def send_activity_to_inbox(recipient: Author, activity: dict):
    """
    Deliver activity to a single recipient's inbox.
    Local recipients → DB inbox insert
    Remote recipients → POST to remote inbox endpoint
    """
    # LOCAL DELIVERY
    if recipient.host.rstrip("/") == settings.SITE_URL.rstrip("/"):
        Inbox.objects.create(author=recipient, data=activity)
        return

    # REMOTE DELIVERY
    inbox_url = f"{recipient.id.rstrip('/')}/inbox/"

    try:
        auth = None
        node = Node.objects.filter(id=recipient.host).first()
        if node and node.auth_user and node.auth_pass:
            auth = (node.auth_user, node.auth_pass)

        requests.post(
            inbox_url,
            data=json.dumps(activity),
            headers={"Content-Type": "application/json"},
            auth=auth,
            timeout=5,
        )
    except Exception as e:
        print(f"[WARN] Failed remote inbox delivery to {inbox_url}: {e}")

def get_followers(author: Author):
    """Return all authors who follow this author (FOLLOW.state=ACCEPTED)."""
    return Author.objects.filter(outgoing_follow_requests__object=author.id, outgoing_follow_requests__state="ACCEPTED"
    )

def get_friends(author):
    """Mutual followers = friends."""
    follower_ids = set(Follow.objects.filter(object=author.id).values_list("actor_id", flat=True))
    following_ids = set(Follow.objects.filter(actor=author).values_list("object", flat=True))
    mutual = follower_ids.intersection(following_ids)
    return Author.objects.filter(id__in=mutual)

def previously_delivered(post):
    """Return all authors who already received this post."""
    inbox_rows = Inbox.objects.filter(data__object__id=str(post.id))
    author_ids = inbox_rows.values_list("author_id", flat=True)
    return Author.objects.filter(id__in=author_ids)

# * ============================================================
# * Main Distributor
# * ============================================================
def distribute_activity(activity: dict, actor: Author):
    """
    Main distribution function for all ActivityPub activities.
    Handles routing for Create/Update/Delete(post),
    Comment, Like, Follow, Undo, ImageAdd/Delete
    and delivers to correct sets of inboxes.
    """

    type_lower = activity.get("type", "").lower()
    obj = activity.get("object")

    # ============================================================
    # 1️⃣ POST CREATION (Create)
    # ============================================================
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

    # ============================================================
    # 2️⃣ POST UPDATE
    # ============================================================
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

    # ============================================================
    # 3️⃣ DELETE POST
    # ============================================================
    if type_lower == "delete" and isinstance(obj, dict) and obj.get("type") == "post":
        recipients = set(get_followers(actor)) | set(get_friends(actor))
        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # ============================================================
    # 4️⃣ COMMENT
    # ============================================================
    if type_lower == "comment" and isinstance(obj, dict):
        entry_author_id = obj.get("entry")

        entry_author = Author.objects.filter(id=entry_author_id).first()
        if not entry_author:
            return

        # Always send to entry owner
        recipients = {entry_author}

        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # ============================================================
    # 5️⃣ LIKE
    # ============================================================
    if type_lower == "like":
        liked_fqid = obj if isinstance(obj, str) else None
        if not liked_fqid:
            return

        # Liked object can be Entry or Comment. We look up its author.
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

    # ============================================================
    # 6️⃣ UNLIKE (Undo(Like))
    # ============================================================
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

    # ============================================================
    # 7️⃣ FOLLOW REQUEST
    # ============================================================
    if type_lower == "follow":
        target_id = obj
        target = Author.objects.filter(id=target_id).first()
        if target:
            send_activity_to_inbox(target, activity)
        return

    # ============================================================
    # 8️⃣ ACCEPT / REJECT FOLLOW
    # ============================================================
    if type_lower in ["accept", "reject"]:
        follow_obj = obj or {}
        follower_id = follow_obj.get("actor")
        follower = Author.objects.filter(id=follower_id).first()

        if follower:
            send_activity_to_inbox(follower, activity)
        return

    # ============================================================
    # 9️⃣ UNFOLLOW → Undo(Follow)
    # ============================================================
    if type_lower == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "follow":
        target_id = obj.get("object")
        target = Author.objects.filter(id=target_id).first()

        if target:
            send_activity_to_inbox(target, activity)
        return

# * ============================================================
# * Inbox Processor
# * ============================================================

def process_inbox(author: Author):
    """
    Process every unprocessed inbox activity for this author.
    This is the ONLY place where the database changes.
    Handles Follow, Accept, Reject, Undo(Follow), Undo(Like),
    Comments, Entries, Likes, and Delete operations.

    NOTE:
    Images are no longer processed here. Remote nodes cannot upload files.
    Image attachments arriving via Create/Update(post) are treated only
    as metadata and will NOT create EntryImage rows.
    """

    inbox_items = Inbox.objects.filter(author=author, processed=False)

    for item in inbox_items:
        activity = item.data
        activity_type = activity.get("type", "").lower()
        obj = activity.get("object")
        actor_id = activity.get("actor")

        # Actor may be local or remote
        actor = Author.objects.filter(id=actor_id).first()

        # ============================================================
        # FOLLOW (Follow request)
        # ============================================================
        if activity_type == "follow":
            follower = actor
            target_id = obj

            if follower and target_id:
                Follow.objects.filter(actor=follower, object=target_id).delete()

                Follow.objects.create(
                    id=activity.get("id"),
                    actor=follower,
                    object=target_id,
                    state="REQUESTED",
                    summary=activity.get("summary", ""),
                    published=parse_datetime(activity.get("published")) or timezone.now()
                )

        # ============================================================
        # ACCEPT (follower_id follows target_id)
        # ============================================================
        elif activity_type == "accept":
            follow_obj = obj or {}
            follower_id = follow_obj.get("actor")
            target_id = follow_obj.get("object")

            follower = Author.objects.filter(id=follower_id).first()
            target = Author.objects.filter(id=target_id).first()

            if follower and target:
                Follow.objects.filter(actor=follower, object=target_id).delete()
                Follow.objects.create(
                    id=activity.get("id"),
                    actor=follower,
                    object=target_id,
                    state="ACCEPTED",
                    summary=activity.get("summary", ""),
                    published=parse_datetime(activity.get("published")) or timezone.now()
                )
                follower.following.add(target)

        # ============================================================
        # REJECT FOLLOW
        # ============================================================
        elif activity_type == "reject":
            follow_obj = obj or {}
            follower_id = follow_obj.get("actor")
            target_id = follow_obj.get("object")

            follower = Author.objects.filter(id=follower_id).first()
            target = Author.objects.filter(id=target_id).first()

            if follower and target:
                Follow.objects.filter(actor=follower, object=target_id).delete()
                Follow.objects.create(
                    id=activity.get("id"),
                    actor=follower,
                    object=target_id,
                    state="REJECTED",
                    summary=activity.get("summary", ""),
                    published=parse_datetime(activity.get("published")) or timezone.now()
                )

        # ============================================================
        # UNFOLLOW (Undo Follow)
        # ============================================================
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "follow":
            follower_id = obj.get("actor")
            target_id = obj.get("object")

            follower = Author.objects.filter(id=follower_id).first()
            target = Author.objects.filter(id=target_id).first()

            if follower and target:
                Follow.objects.filter(actor=follower, object=target_id).delete()
                follower.following.remove(target)

        # ============================================================
        # REMOVE FRIEND (custom)
        # ============================================================
        elif activity_type == "removefriend":
            target_id = obj
            target = Author.objects.filter(id=target_id).first()
            initiator = actor

            if initiator and target:
                initiator.following.remove(target)
                target.following.remove(initiator)
                Follow.objects.filter(actor=initiator, object=target_id).delete()
                Follow.objects.filter(actor=target, object=initiator.id).delete()

        # ============================================================
        # ENTRY CREATE (post)
        # Remote attachments are NOT saved as EntryImage.
        # ============================================================
        elif activity_type == "create" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")

            Entry.objects.update_or_create(
                id=entry_id,
                defaults={
                    "title": obj.get("title", ""),
                    "content": obj.get("content", ""),
                    "contentType": obj.get("contentType", "text/plain"),
                    "author": actor or author,
                    "visibility": obj.get("visibility", "PUBLIC"),
                    "published": parse_datetime(obj.get("published")) or timezone.now(),
                }
            )
            # NOTE: obj.get("attachments") are preserved in content/HTML only.

        # ============================================================
        # ENTRY UPDATE (post)
        # Remote attachments are NOT converted into EntryImage rows.
        # ============================================================
        elif activity_type == "update" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")
            entry = Entry.objects.filter(id=entry_id).first()

            if entry:
                entry.title = obj.get("title", entry.title)
                entry.content = obj.get("content", entry.content)
                entry.contentType = obj.get("contentType", entry.contentType)
                entry.visibility = obj.get("visibility", entry.visibility)
                entry.save()
                # NOTE: attachments ignored—remote nodes cannot upload files.

        # ============================================================
        # ENTRY DELETE (post)
        # ============================================================
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")
            entry = Entry.objects.filter(id=entry_id).first()
            if entry:
                entry.visibility = "DELETED"
                entry.save()

        # ============================================================
        # COMMENT CREATE
        # ============================================================
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

        # ============================================================
        # DELETE COMMENT
        # ============================================================
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "comment":
            Comment.objects.filter(id=obj.get("id")).delete()

        # ============================================================
        # LIKE
        # ============================================================
        elif activity_type == "like":
            obj_id = activity.get("object")

            Like.objects.filter(author=actor, object=obj_id).delete()
            Like.objects.create(
                id=activity.get("id"),
                author=actor,
                object=obj_id,
                published=parse_datetime(activity.get("published")) or timezone.now()
            )

        # ============================================================
        # UNLIKE (Undo Like)
        # ============================================================
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "like":
            Like.objects.filter(author=obj.get("actor"), object=obj.get("object")).delete()

        # ============================================================
        # UNKNOWN ACTIVITY — safely ignored
        # ============================================================
        else:
            pass

        # Mark processed
        item.processed = True
        item.save()
