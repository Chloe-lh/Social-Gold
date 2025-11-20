import requests
from django.utils import timezone
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox


def push_local_inbox(author, activity):
    """Push activity to a local inbox (DB only)."""
    Inbox.objects.create(author=author, data=activity)


def push_remote_inbox(url, activity):
    """
    Push activity to a remote node's inbox URL.
    You can enhance this with HTTP signature + auth later.
    """
    try:
        resp = requests.post(url, json=activity, timeout=5)
        resp.raise_for_status()
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


def send_activity(author_list, activity):
    """Send to multiple authors, local or remote."""
    for author in author_list:
        if author.local:  # local node
            push_local_inbox(author, activity)
        else:  # remote node
            inbox_url = author.inbox_url  # store this field on Author
            push_remote_inbox(inbox_url, activity)

def distribute_activity(activity, actor):
    """
    Deliver activity to all appropriate inboxes based on type + visibility.
    actor = Author instance who created the activity.
    activity = dict representation of activity (entry, comment, like, follow)
    """

    type = activity.get("type", "").lower()
    visibility = activity.get("object", {}).get("visibility", "PUBLIC").upper()
    post_id = activity.get("object", {}).get("id")
    post = Post.objects.filter(id=post_id).first() if post_id else None

    if type in ["create", "entry", "post"]:
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

    if type == "follow":
        # push to target's inbox
        target_id = activity.get("object")
        target = Author.objects.filter(id=target_id).first()
        if target:
            send_activity([target], activity)
        return

    if type == "follow-back":
        target_id = activity.get("object")
        target = Author.objects.filter(id=target_id).first()
        if target:
            # push to both friend and actor
            send_activity([target, actor], activity)
        return

