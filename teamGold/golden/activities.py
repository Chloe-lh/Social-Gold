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
    # Extract the host from the author_id (e.g., 'http://127.0.0.1:8000' or 'https://your-heroku-app.herokuapp.com')
    author_host = urlparse(author_id).netloc

    # Extract the host from the site's base URL (settings.SITE_URL, e.g., '127.0.0.1:8000' or 'your-heroku-app.herokuapp.com')
    site_host = urlparse(settings.SITE_URL).netloc

    # If the host of the author_id matches the host of the site, it's local
    return author_host == site_host

def push_remote_inbox(inbox_url, activity):
    """ Function to send an activity to a remote author's inbox. """
    try:
        response = requests.post(inbox_url, json=activity, timeout=5)
        if response.status_code != 200:
            print(f"Error sending activity to {inbox_url}: {response.status_code}")
        else:
            print(f"Successfully sent activity to {inbox_url}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending activity to remote inbox: {e}")

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

    # If target is remote, send the activity to their inbox
    if not is_local(entry.author.id):
        push_remote_inbox(entry.author.inbox_url, activity)  # Send activity to remote author's inbox.
    
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

    if not is_local(entry.author.id):
        push_remote_inbox(entry.author.inbox_url, activity)  # Send activity to remote author's inbox.
    
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

    if not is_local(entry.author.id):
        push_remote_inbox(entry.author.inbox_url, activity)  # Send activity to remote author's inbox.

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

    if not is_local(entry.author.id):
        push_remote_inbox(entry.author.inbox_url, activity)  # Send activity to remote author's inbox.

    return activity

def create_like_activity(author, liked_object_fqid):
    activity_id = make_fqid(author, "likes")

    activity = {
        "type": "Like",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} liked an entry",
        "object": str(liked_object_fqid)  # Entry.id or Comment.id
    }

    # If liked object is remote, send the activity to the inbox
    if not is_local(liked_object_fqid):
        push_remote_inbox(liked_object_fqid, activity)  # Send activity to remote author's inbox.
    
    return activity

def create_follow_activity(author, target):
    """
    Creates a follow activity when author wants to follow target.
    """
    activity = {
        "type": "Follow", 
        "actor": {
            "type": "author",
            "id": author.id,
            "host": author.host,
            "displayName": author.username,
            "profileImage": author.profileImage if author.profileImage else None,
        },
        "object": {
            "type": "author",
            "id": target.id,
            "host": target.host,
            "displayName": target.username,
            "profileImage": target.profileImage if target.profileImage else None,
        },
    }
    if not is_local(target.id):
        push_remote_inbox(target.inbox_url, activity)
    return activity

'''
def create_follow_activity(author, target):
    activity = {
        "type": "Follow", 
        "actor": {
            "type": "author",
            "id": author.id,
            "host": author.host,
            "displayName": author.username,
            "profileImage": author.profileImage if author.profileImage else None,
        },
        "object": {
            "type": "author",
            "id": target.id,
            "host": target.host,
            "displayName": target.username,
            "profileImage": target.profileImage if target.profileImage else None,
        },
    }

    if not is_local(target.id): # If target is remote
        try:
            push_remote_inbox(target.inbox_url, activity) 
            print(f"Remote activity successfully pushed to {target.inbox_url}")
        except Exception as e:
            print(f"Error sending activity to remote inbox: {e}")
    else:
        print(f"Local activity, no remote push needed for {target.username}")

    return activity
'''

def create_accept_follow_activity(acceptor_author, follower_id):
    activity_id = make_fqid(acceptor_author, "accept")
    follower_host = str(follower_id).split("/api/authors/")[0]  # Check if the follower is local

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
        "state": "ACCEPTED",
        "published": timezone.now().isoformat(),
        "target_is_local": follower_host == acceptor_author.host,
    }

    if not is_local(follower_id):
        push_remote_inbox(follower_id, activity)
    
    return activity

def create_reject_follow_activity(acceptor_author, follower_id):
    activity_id = make_fqid(acceptor_author, "reject")
    follower_host = str(follower_id).split("/api/authors/")[0]  # Check if the follower is local

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
        "state": "REJECTED",
        "published": timezone.now().isoformat(),
        "target_is_local": follower_host == acceptor_author.host,
    }

    if not is_local(follower_id):
        push_remote_inbox(follower_id, activity)
    
    return activity

def create_unfollow_activity(actor_author, target_id):
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
        "target_is_local": target_id.startswith(actor_author.host),
    }

    if not is_local(target_id):
        push_remote_inbox(target_id, activity)
    
    return activity

def create_unfriend_activity(actor_author, target_id):
    activity_id = make_fqid(actor_author, "unfriend")

    activity = {
        "type": "RemoveFriend",
        "id": activity_id,
        "summary": f"{actor_author.username} removed you as a friend",
        "actor": str(actor_author.id),
        "object": str(target_id),
        "published": timezone.now().isoformat(),
        "target_is_local": target_id.startswith(actor_author.host),
    }

    if not is_local(target_id):
        push_remote_inbox(target_id, activity)
    
    return activity

def create_profile_update_activity(actor_author):
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
        "target_is_local": True,
    }

    return activity

def create_unlike_activity(author, liked_object_fqid):
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
        "target_is_local": liked_object_fqid.startswith(author.host),
    }

    if not is_local(liked_object_fqid):
        push_remote_inbox(liked_object_fqid, activity)
    
    return activity

def create_delete_comment_activity(author, comment):
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

    if not is_local(comment.author.id):
        push_remote_inbox(comment.author.inbox_url, activity)
    
    return activity
