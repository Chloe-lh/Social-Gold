"""
This module centralizes the creation of ActivityPub-style activity objects
using dictionary architecture. Since views should never hand-build JSON as 
required in the course, we should call these helper functions to 
produce the activity needed, then pass them through distribute_activity().

* All activities need to follow a consistent model s.t it references the model instance and/or FQIDs as input
"""


def make_fqid(author, suffix: str):
    """
    Example:
      author.id = https://yoursite/api/authors/<uuid>
      return =   https://yoursite/api/authors/<uuid>/<suffix>/<uuid>
    """
    return f"{author.id.rstrip('/')}/{suffix}/{uuid.uuid4()}"


def make_image_fqid(author):
    return f"{author.id.rstrip('/')}/images/{uuid.uuid4()}"


def create_new_entry_activity(author, entry):

    activity_id = make_fqid(author, "posts")

    return {
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
        }
    }


def create_update_entry_activity(author, entry):

    activity_id = make_fqid(author, "posts")

    return {
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
        },
    }


def create_delete_entry_activity(author, entry):

    activity_id = make_fqid(author, "posts")

    return {
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


def create_image_add_activity(author, entry, image):
    activity_id = make_fqid(author, "images")

    return {
        "type": "AddImage",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} added an image",
        "object": {
            "type": "image",
            "id": str(image.id),       
            "entry": str(entry.id),
            "name": image.name,
            "url": image.image.url,
            "order": image.order,
            "uploaded_at": image.uploaded_at.isoformat(),
        }
    }


def create_image_update_activity(author, entry, image):
    activity_id = make_fqid(author, "images")

    return {
        "type": "UpdateImage",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} updated an image",
        "object": {
            "type": "image",
            "id": str(image.id),
            "entry": str(entry.id),
            "name": image.name,
            "url": image.image.url,
            "order": image.order,
            "uploaded_at": image.uploaded_at.isoformat(),
        }
    }


def create_image_delete_activity(author, entry, image):
    activity_id = make_fqid(author, "images")

    return {
        "type": "DeleteImage",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} deleted an image",
        "object": {
            "type": "image",
            "id": str(image.id),
            "entry": str(entry.id)
        }
    }


def create_comment_activity(author, entry, comment):
    """
    Comments must already have: id, author, entry, content, etc.
    """
    activity_id = make_fqid(author, "comments")

    return {
        "type": "Comment",
        "id": activity_id,
        "actor": str(author.id), # author is the person who commented
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


def create_like_activity(author, liked_object_fqid):
    activity_id = make_fqid(author, "likes")

    return {
        "type": "Like",
        "id": activity_id,
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "summary": f"{author.username} liked an entry",
        "object": str(liked_object_fqid) # Entry.id or Comment.id
    }














def create_follow_activity(actor_author, target_id):
    """
    Creates a Follow activity where actor_author requests to follow target_id.
    """
    activity_id = make_fqid(actor_author, "follow")

    return {
        "type": "Follow",
        "id": activity_id,
        "summary": f"{actor_author.username} wants to follow you",
        "actor": str(actor_author.id),       # FQID
        "object": str(target_id),            # FQID of target
        "published": timezone.now().isoformat(),
        "state": "REQUESTED",
        "target_is_local": target_id.startswith(actor_author.host),
    }


def create_follow_activity(actor_author, target_id):
    """
    Creates a Follow activity where actor_author requests to follow target_id.
    """
    activity_id = make_fqid(actor_author, "follow")

    return {
        "type": "Follow",
        "id": activity_id,
        "summary": f"{actor_author.username} wants to follow you",
        "actor": str(actor_author.id),       # FQID
        "object": str(target_id),            # FQID of target
        "published": timezone.now().isoformat(),
        "state": "REQUESTED",
        "target_is_local": target_id.startswith(actor_author.host),
    }

def create_accept_follow_activity(acceptor_author, follower_id):
    """
    Creates an Accept activity to send back to the requestor.
    """
    activity_id = make_fqid(acceptor_author, "accept")

    return {
        "type": "Accept",
        "id": activity_id,
        "summary": f"{acceptor_author.username} accepted your follow request",
        "actor": str(acceptor_author.id),
        "object": {
            "type": "Follow",
            "actor": follower_id,
            "object": str(acceptor_author.id),
        },
        "state": "ACCEPTED",
        "published": timezone.now().isoformat(),
        "target_is_local": follower_id.startswith(acceptor_author.host),
    }

def create_reject_follow_activity(acceptor_author, follower_id):
    """
    Creates a Reject activity sent back to the follower.
    """
    activity_id = make_fqid(acceptor_author, "reject")

    return {
        "type": "Reject",
        "id": activity_id,
        "summary": f"{acceptor_author.username} rejected your follow request",
        "actor": str(acceptor_author.id),
        "object": {
            "type": "Follow",
            "actor": follower_id,
            "object": str(acceptor_author.id),
        },
        "state": "REJECTED",
        "published": timezone.now().isoformat(),
        "target_is_local": follower_id.startswith(acceptor_author.host),
    }


def create_unfollow_activity(actor_author, target_id):
    """
    Creates an Undo activity that reverses a Follow.
    """
    activity_id = make_fqid(actor_author, "undo-follow")

    return {
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

def create_unfriend_activity(actor_author, target_id):
    """
    Creates a Remove-Friend activity (custom).
    You will handle this in process_inbox() by removing mutual follows.
    """
    activity_id = make_fqid(actor_author, "unfriend")

    return {
        "type": "RemoveFriend",
        "id": activity_id,
        "summary": f"{actor_author.username} removed you as a friend",
        "actor": str(actor_author.id),
        "object": str(target_id),
        "published": timezone.now().isoformat(),
        "target_is_local": target_id.startswith(actor_author.host),
    }

def create_profile_update_activity(actor_author):
    """
    Sends a profile-update activity to sync profile changes.
    """
    activity_id = make_fqid(actor_author, "profile-update")

    return {
        "type": "Update",
        "id": activity_id,
        "summary": f"{actor_author.username} updated their profile",
        "actor": str(actor_author.id),
        "object": {
            "type": "Author",
            "id": str(actor_author.id),
        },
        "published": timezone.now().isoformat(),
        "target_is_local": True,  # Usually broadcast to followers
    }


