import requests
from django.utils import timezone
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox
from golden.services import is_local
from urllib.parse import urljoin


def push_local_inbox(author, activity):
    """Push activity to a local inbox (DB only)."""
    Inbox.objects.create(author=author, data=activity)


def push_remote_inbox(url, activity):
    """
    Push activity to a remote node's inbox URL.
    """
    try:
        print("gets here)")
        resp = requests.post(url, json=activity, timeout=5)
        print("gets here 2")
        resp.raise_for_status()
        print("gets here 3")
        return True
    except requests.RequestException:
        return False


def get_followers(author):
    """Return all authors following this author (who receive PUBLIC posts)."""
    follower_ids = Follow.objects.filter(target=author).values_list("actor_id", flat=True)
    return Author.objects.filter(id__in=follower_ids)


def get_friends(author):
    """Mutual followers = friends."""
    followers = set(Follow.objects.filter(target=author).values_list("actor_id", flat=True))
    following = set(Follow.objects.filter(actor=author).values_list("target_id", flat=True))
    friend_ids = followers.intersection(following)
    return Author.objects.filter(id__in=friend_ids)


def previously_delivered(post):
    """Return all authors who already received this post."""
    inbox_rows = Inbox.objects.filter(data__object__id=str(post.id))
    author_ids = inbox_rows.values_list("author_id", flat=True)
    return Author.objects.filter(id__in=author_ids)


def send_activity(target_id, activity):
    """
    Send an activity to a single target (local or remote).
    """
    
    target_author = Author.objects.filter(id=target_id).first()

    if target_author:
        # Local author: store in DB inbox
        Inbox.objects.create(author=target_author, data=activity)
    else:
        # Remote author: build inbox URL from FQID
        inbox_url = urljoin(target_id, "inbox/")
        print(inbox_url)
        push_remote_inbox(inbox_url, activity)

def distribute_activity(activity, actor):
    """
    Deliver activity to all appropriate inboxes based on type + visibility.
    actor = Author instance who created the activity.
    activity = dict representation of activity (entry, comment, like, follow)
    """

    type = activity.get("type", "").lower()

    if type in ["create", "entry", "post"]:
        visibility = activity.get("object", {}).get("visibility", "PUBLIC").upper()
        if visibility == "PUBLIC":
            # send to all followers + friends
            recipients = set(get_followers(actor)) | set(get_friends(actor))
            send_activity(recipients, activity)
        elif visibility == "UNLISTED":
            # only followers
            send_activity(get_followers(actor), activity)
        elif visibility == "FRIENDS":
            # only friends
            send_activity(get_friends(actor), activity)
        return

    if type == "update" and post:
        past = previously_delivered(post)
        if visibility in ["PUBLIC", "UNLISTED"]:
            recipients = set(get_followers(actor))
            if visibility == "PUBLIC":
                recipients |= set(get_friends(actor))
        elif visibility == "FRIENDS":
            recipients = set(get_friends(actor))

        # also push to anyone who received it before
        recipients |= set(past)
        send_activity(recipients, activity)
        return

    if type == "delete" and post:
        past = previously_delivered(post)
        if visibility in ["PUBLIC", "UNLISTED"]:
            recipients = set(get_followers(actor))
            if visibility == "PUBLIC":
                recipients |= set(get_friends(actor))
        elif visibility == "FRIENDS":
            recipients = set(get_friends(actor))

        # also push to anyone who received it before
        recipients |= set(past)
        send_activity(recipients, activity)
        return

    if type == "comment" and post:
        # always push to post author
        recipients = {post.author}
        if visibility in ["PUBLIC", "UNLISTED"]:
            recipients |= set(get_followers(post.author))
        elif visibility == "FRIENDS":
            recipients |= set(get_friends(post.author))

        send_activity(recipients, activity)
        return

    if type == "like" and post:
        recipients = {post.author}
        if visibility in ["PUBLIC", "UNLISTED"]:
            recipients |= set(get_followers(post.author))
        elif visibility == "FRIENDS":
            recipients |= set(get_friends(post.author))
        send_activity(recipients, activity)
        return

    if type == "follow" or type == "process_decision":
        # push to target's inbox
        target_id = activity.get("object")
        send_activity(target_id, activity)
        return

def process_inbox(author):
    """Process all unprocessed activities in this author's inbox."""
    inbox_items = Inbox.objects.filter(author=author, processed=False)

    if not inbox_items.exists():
        for item in inbox_items:
            activity = item.data
            activity_type = activity.get("type", "").lower()

            if activity_type == "follow":
                # Extract actor and object
                actor_id = activity.get("author")
                actor_author = Author.objects.filter(id=actor_id).first()

                # Create Follow request in DB if it doesn't exist
                follow, created = Follow.objects.get_or_create(
                    actor=actor_author,
                    object=author,
                    defaults={
                        "id": activity.get("id") or f"{actor_author.id}/follow/{uuid.uuid4()}",
                        "summary": activity.get("summary", ""),
                        "published": activity.get("published", timezone.now()),
                        "state": activity.get("state", "REQUESTED")
                    }
                )

            elif activity_type == "process_decision":
                actor_id = activity.get("object")
                actor_author = Author.objects.filter(id=actor_id).first()
                state = activity.get("state")
                target_id = activity.get("author")
                target_author = Author.objects.filter(id=target_id).first()
                if not target_author:
                    # Cannot update table if target author does not exist locally
                    return
                if state == "ACCEPTED":
                    actor_author.following.add(target_author)
                #if state == "REJECTED" -> have to update this

            elif activity_type in ["create", "post", "entry"]:
                # Handle posts: create or update local Entry table
                from golden.models import Entry
                obj = activity.get("object", {})
                Entry.objects.update_or_create(
                    id=obj.get("id"),
                    defaults={
                        "title": obj.get("title", ""),
                        "content": obj.get("content", ""),
                        "contentType": obj.get("contentType", "text/plain"),
                        "author": author,
                        "visibility": obj.get("visibility", "PUBLIC"),
                        "published": obj.get("published", timezone.now()),
                    }
                )

            elif activity_type == "like":
                # Similar: handle likes
                from golden.models import Like, Entry
                entry_id = activity.get("object")
                entry = Entry.objects.filter(id=entry_id).first()
                if entry:
                    Like.objects.get_or_create(
                        id=activity.get("id") or f"{author.id}/like/{uuid.uuid4()}",
                        entry=entry,
                        author=author,
                        published=activity.get("published", timezone.now())
                    )

            elif activity_type == "comment":
                # Handle comments
                from golden.models import Comment, Entry
                obj = activity.get("object", {})
                entry = Entry.objects.filter(id=obj.get("id")).first()
                if entry:
                    Comment.objects.get_or_create(
                        id=activity.get("id") or f"{author.id}/comment/{uuid.uuid4()}",
                        entry=entry,
                        author=author,
                        content=obj.get("content", ""),
                        contentType=obj.get("contentType", "text/plain"),
                        published=activity.get("published", timezone.now())
                    )

            else:
                raise ValueError(f"Unrecognized activity type: '{activity.get('type')}'")

            # Mark the inbox item as processed
            item.processed = True
            item.save()