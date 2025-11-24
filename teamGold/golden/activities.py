import uuid
from django.utils import timezone
from django.conf import settings
from urllib.parse import urlparse
from golden.models import Follow
import requests
from django.conf import settings

node_url = settings.SITE_URL

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

    commentList = get_comment_list_api(entry.id)
    likeList = get_like_api(entry.id)
    activity = {
        "type": "Entry",
        "title" : entry.title,
        "id": activity_id,
        "web" : entry.web,
        "description" : entry.description,
        "contentType": entry.contentType,
        "content": entry.content,
        "author":{"type":"author",
            "id":author.id,
            "host":author.host,
            "displayName":author.username,
            "web": author.web,
            "github": author.github,
            "profileImage":author.profileImage.url if author.profileImage else None
            },

        "comments": {},
        "likes": {}, 
        "published":entry.published,
        "visibility": entry.visibility,


    }
    
    return activity

def create_update_entry_activity(author, entry):
    activity_id = make_fqid(author, "posts")
    commentList = get_comment_list_api(entry.id)
    likeList = get_like_api(entry.id)
   
    
    activity = {
        "type": "Entry",
        "title" : entry.title,
        "id": activity_id,
        "web" : entry.web,
        "description" : entry.description,
        "contentType": entry.contentType,
        "content": entry.content,
        "author":{"type":"author",
            "id":author.id,
            "host":author.host,
            "displayName":author.username,
            "web": author.web,
            "github": author.github,
            "profileImage":author.profileImage.url if author.profileImage else None
            },

        "comments":commentList,
        "likes": likeList,
        "published":entry.published,
        "visibility": entry.visibility,
    }
    
    return activity

def create_delete_entry_activity(author, entry):
    activity_id = make_fqid(author, "posts")
    commentList = get_comment_list_api(entry.id)
    likeList = get_like_api(entry.id)
   
    activity = {
        "type": "Entry",
        "title" : entry.title,
        "id": activity_id,
        "web" : entry.web,
        "description" : entry.description,
        "contentType": entry.contentType,
        "content": entry.content,
        "author":{"type":"author",
            "id":author.id,
            "host":author.host,
            "displayName":author.username,
            "web": author.web,
            "github": author.github,
            "profileImage":author.profileImage.url if author.profileImage else None
            },

        "comments":commentList,
        "likes": likeList,
        "published":entry.published,
        "visibility": "DELETED", # this is possibly where u can delete
    }
    return activity

def create_comment_activity(author, entry, comment):
    return {
        "type": "comment",
        "id": comment.id,                      
        "actor": {
            "id": author.id,
            "host": author.host,
            "username": author.username,
        },
        "object": {
            "type": "comment",
            "id": comment.id,                   
            "entry": entry.id,
            "content": comment.content,
            "contentType": comment.contentType,
            "author": {
                "id": author.id,
                "host": author.host,
                "username": author.username,
            },
            "published": comment.published.isoformat(),
        },
        "published": comment.published.isoformat(),
    }

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
    
    print(f"[DEBUG create_follow_activity] Creating follow activity: actor={author.username} (id={author.id}), target={target.username} (id={target.id})")
    
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
    
    print(f"[DEBUG create_follow_activity] Activity created: id={activity_id}, type={activity['type']}, object={activity['object']}")
    
    return activity

def create_accept_follow_activity(acceptor_author, follower_id_or_follow_id):
    """
    Create an Accept activity for a follow request.
    Accepts either a follower Author ID string or a Follow ID string.
    If a Follow ID is provided, it will look up the Follow object to get the follower.
    """
    follower_id = follower_id_or_follow_id
    follow_obj = None
    
    follow_obj = Follow.objects.filter(id=follower_id_or_follow_id).first()
    if follow_obj:
        follower_id = str(follow_obj.actor.id)
        follow_id = follow_obj.id
    else:
        follow_id = None
    
    activity_id = make_fqid(acceptor_author, "accept")

    if follow_id:
        activity = {
            "type": "Accept",
            "id": activity_id,
            "summary": f"{acceptor_author.username} accepted your follow request",
            "actor": str(acceptor_author.id),
            "object": follow_id, 
            "published": timezone.now().isoformat(),
        }
    else:
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

    follower_id = follower_id_or_follow_id
    follow_obj = None
    
    follow_obj = Follow.objects.filter(id=follower_id_or_follow_id).first()
    if follow_obj:
        follower_id = str(follow_obj.actor.id)
        follow_id = follow_obj.id
    else:
        follow_id = None
    
    activity_id = make_fqid(acceptor_author, "reject")

    if follow_id:
        activity = {
            "type": "Reject",
            "id": activity_id,
            "summary": f"{acceptor_author.username} rejected your follow request",
            "actor": str(acceptor_author.id),
            "object": follow_id, 
            "published": timezone.now().isoformat(),
        }
    else:
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
    activity_id = make_fqid(author, "unlike")

    activity = {
        "type": "unlike",
        "id": activity_id,
        "summary": f"{author.username} unliked an entry or comment",
        "actor": str(author.id),
        "published": timezone.now().isoformat(),
        "object": str(liked_object_fqid) 
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



'''
HELPER FUNCTIONS
'''

def get_comment_list_api(entry_id):
    base = settings.SITE_URL.rstrip('/') + '/'
    url = f"{base}api/Entry/{entry_id}/comments/"

    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print("Error fetching comment list:", e)
        return None
    
def get_like_api(like_id):
    base = settings.SITE_URL.rstrip('/') + '/'
    url = f"{base}api/Like/{like_id}/"

    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print("Error fetching like:", e)
        return None