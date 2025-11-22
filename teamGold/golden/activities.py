import uuid
from django.utils import timezone
import requests
from urllib.parse import urlparse
from django.conf import settings

def make_fqid(author, suffix: str):
    """
    Example:
      author.id = https://yoursite/api/authors/<uuid>
      return =   https://yoursite/api/authors/<uuid>/<suffix>/<uuid>
    """
    return f"{author.id.rstrip('/')}/{suffix}/{uuid.uuid4()}"


def is_local(author_id):
    """
    Determines if the given author_id belongs to a local author or a remote one.
    Compares the host portion of the author_id URL with the current site's host.
    """
    author_host = urlparse(author_id).netloc
    site_host = urlparse(settings.SITE_URL).netloc
    return author_host == site_host


def create_new_entry_activity(author, entry):
    activity_id = make_fqid(author, "posts")

    activity = {
        "type": "Create",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} created a new entry",
        "object": {
            "type": "post",
            "id": str(entry.id),
            "title": entry.title,
            "content": entry.content,
            "contentType": entry.contentType,
            "visibility": entry.visibility,
            "published": entry.published.isoformat(),
            "author": str(author.id),
            "attachments": [
                {
                    "type": "Image",
                    "mediaType": "image/jpeg",
                    "name": img.name,
                    "url": img.image.url,
                    "order": img.order,
                }
                for img in entry.images.all()
            ]
        }
    }
    
    return activity


def create_update_entry_activity(author, entry):
    activity_id = make_fqid(author, "posts")

    activity = {
        "type": "Update",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} updated their entry",
        "object": {
            "type": "post",
            "id": str(entry.id),
            "title": entry.title,
            "content": entry.content,
            "contentType": entry.contentType,
            "visibility": entry.visibility,
            "published": entry.published.isoformat(),
            "author": str(author.id),
            "attachments": [
                {
                    "type": "Image",
                    "mediaType": "image/jpeg",
                    "name": img.name,
                    "url": img.image.url,
                    "order": img.order,
                }
                for img in entry.images.all()
            ]
        }
    }
    
    return activity


def create_delete_entry_activity(author, entry):
    activity_id = make_fqid(author, "posts")

    activity = {
        "type": "Delete",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} deleted an entry",
        "object": {
            "type": "post",
            "id": str(entry.id),
        },
    }

    return activity


def create_comment_activity(author, entry, comment):
    activity_id = make_fqid(author, "comments")

    activity = {
        "type": "Comment",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} commented on an entry",
        "object": {
            "type": "comment",
            "id": str(comment.id),
            "entry": str(entry.id),  
            "author": str(author.id),
            "content": comment.content,
            "contentType": comment.contentType,
            "published": comment.published.isoformat(),
        }
    }

    return activity


def create_like_activity(author, liked_object_fqid):
    activity_id = make_fqid(author, "likes")

    activity = {
        "type": "Like",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} liked an entry",
        "object": str(liked_object_fqid)
    }
    
    return activity


def create_follow_activity(author, target):
    """
    Creates a follow activity when author wants to follow target.
    Format matches ActivityPub specification.
    """
    activity_id = make_fqid(author, "follow")
    
    activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Follow",
        "id": activity_id,
        "summary": f"{author.username} wants to follow you",
        "actor": str(author.id),
        "object": str(target.id),
        "published": timezone.now().isoformat(),
        "state": "REQUESTED",
    }
    
    return activity


def create_accept_follow_activity(acceptor_author, follower_id_or_follow_id):
    """
    Create an Accept activity for a follow request.
    Accepts either a follower Author ID string or a Follow ID string.
    If a Follow ID is provided, it will look up the Follow object to get the follower.
    """
    from golden.models import Follow
    
    # Check if follower_id_or_follow_id is a Follow ID (contains '/follow/')
    # or try to look it up as a Follow ID first
    follower_id = follower_id_or_follow_id
    follow_obj = None
    
    # Try to find it as a Follow ID
    follow_obj = Follow.objects.filter(id=follower_id_or_follow_id).first()
    if follow_obj:
        follower_id = str(follow_obj.actor.id)
        follow_id = follow_obj.id
    else:
        # It's likely an Author ID, use it directly
        follow_id = None
    
    activity_id = make_fqid(acceptor_author, "accept")

    # Create activity - use Follow ID if available, otherwise use object structure
    if follow_id:
        # Reference the original Follow activity by ID (preferred for ActivityPub)
        activity = {
            "type": "Accept",
            "id": activity_id,
            "summary": f"{acceptor_author.username} accepted your follow request",
            "actor": str(acceptor_author.id),
            "object": follow_id,  # Reference the Follow activity by ID
            "published": timezone.now().isoformat(),
        }
    else:
        # Fallback to object structure if Follow ID not available
        activity = {
            "type": "Accept",
            "id": activity_id,
            "summary": f"{acceptor_author.username} accepted your follow request",
            "actor": str(acceptor_author.id),
            "object": {
                "type": "Follow",
                "actor": str(follower_id),
                "object": str(acceptor_author.id),
            },
            "published": timezone.now().isoformat(),
        }
    
    return activity


def create_reject_follow_activity(acceptor_author, follower_id_or_follow_id):
    """
    Create a Reject activity for a follow request.
    Accepts either a follower Author ID string or a Follow ID string.
    If a Follow ID is provided, it will look up the Follow object to get the follower.
    """
    from golden.models import Follow
    
    # Check if follower_id_or_follow_id is a Follow ID (contains '/follow/')
    # or try to look it up as a Follow ID first
    follower_id = follower_id_or_follow_id
    follow_obj = None
    
    # Try to find it as a Follow ID
    follow_obj = Follow.objects.filter(id=follower_id_or_follow_id).first()
    if follow_obj:
        follower_id = str(follow_obj.actor.id)
        follow_id = follow_obj.id
    else:
        # It's likely an Author ID, use it directly
        follow_id = None
    
    activity_id = make_fqid(acceptor_author, "reject")

    # Create activity - use Follow ID if available, otherwise use object structure
    if follow_id:
        # Reference the original Follow activity by ID (preferred for ActivityPub)
        activity = {
            "type": "Reject",
            "id": activity_id,
            "summary": f"{acceptor_author.username} rejected your follow request",
            "actor": str(acceptor_author.id),
            "object": follow_id,  # Reference the Follow activity by ID
            "published": timezone.now().isoformat(),
        }
    else:
        # Fallback to object structure if Follow ID not available
        activity = {
            "type": "Reject",
            "id": activity_id,
            "summary": f"{acceptor_author.username} rejected your follow request",
            "actor": str(acceptor_author.id),
            "object": {
                "type": "Follow",
                "actor": str(follower_id),
                "object": str(acceptor_author.id),
            },
            "published": timezone.now().isoformat(),
        }
    
    return activity


def create_unfollow_activity(actor_author, target_id):
    """
    Create an Undo Follow activity.
    """
    activity_id = make_fqid(actor_author, "undo-follow")

    activity = {
        "type": "Undo",
        "id": activity_id,
        "summary": f"{actor_author.username} stopped following you",
        "actor": str(actor_author.id),
        "object": {
            "type": "Follow",
            "actor": str(actor_author.id),
            "object": str(target_id)
        },
        "published": timezone.now().isoformat(),
    }
    
    return activity


def create_unfriend_activity(actor_author, target_id):
    """
    Create a RemoveFriend activity.
    """
    activity_id = make_fqid(actor_author, "unfriend")

    activity = {
        "type": "RemoveFriend",
        "id": activity_id,
        "summary": f"{actor_author.username} removed you as a friend",
        "actor": str(actor_author.id),
        "object": str(target_id),
        "published": timezone.now().isoformat(),
    }
    
    return activity


def create_profile_update_activity(actor_author):
    """
    Create a profile update activity.
    """
    activity_id = make_fqid(actor_author, "profile-update")

    activity = {
        "type": "Update",
        "id": activity_id,
        "summary": f"{actor_author.username} updated their profile",
        "actor": str(actor_author.id),
        "object": {
            "type": "Author",
            "id": str(actor_author.id),
        },
        "published": timezone.now().isoformat(),
    }

    return activity


def create_unlike_activity(author, liked_object_fqid):
    """
    Create an Undo Like activity.
    """
    activity_id = make_fqid(author, "undo-like")

    activity = {
        "type": "Undo",
        "id": activity_id,
        "summary": f"{author.username} unliked an entry or comment",
        "actor": str(author.id),
        "object": {
            "type": "Like",
            "actor": str(author.id),
            "object": str(liked_object_fqid)
        },
        "published": timezone.now().isoformat(),
    }
    
    return activity


def create_delete_comment_activity(author, comment):
    """
    Create a delete comment activity.
    """
    activity_id = make_fqid(author, "comments")

    activity = {
        "type": "Delete",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} deleted a comment",
        "object": {
            "type": "comment",
            "id": str(comment.id)
        }
    }
    
    return activity