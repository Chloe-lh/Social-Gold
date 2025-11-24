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
    activity_id = make_fqid(author, "comments")
    activity = {
        "type": "comment",
        "author":{
            "type":"author",
            "id":author.id,
            "web":author.web,
            "host":author.host,
            "displayName":author.name,
            "github":author.github,
            "profileImage":author.profileImage.url if author.profileImage else None,
        },
        "comment":comment.content,
        "contentType":comment.contentType,
        "published":comment.published,
        "id":activity_id,
        "entry":entry.id,
        "likes":{},
    }
    return activity

def create_like_activity(author, liked_object_fqid):
    activity_id = make_fqid(author, "likes")

    activity = {
        "type": "like",
        "author":{
            "type":"author",
            "id":author.id,
            "web":author.web,
            "host":author.host,
            "displayName":author.name,
            "github":author.github,
            "profileImage":author.profileImage.url if author.profileImage else None,
        },
        "published":timezone.now().isoformat(),
        "id":activity_id,
        "object":liked_object_fqid,
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
        "type":"follow",
        "summary":f"{author.name} wants to follow {target.name}",
        "actor":{
            "type":"author",
            "id":author.id,
            "host":author.host,
            "displayName":author.username,
            "github": author.github,
            "profileImage":author.profileImage.url if author.profileImage else None,
            # URL of the user's HTML profile page
            "web": author.web
        },
        #"actor": str(author.id),
        "object": {
            "type":"author",
            "id":target.id,
            "host":target.host,
            "displayName":target.username,
            "github": target.github,
            "profileImage":target.profileImage.url if target.profileImage else None,
            # URL of the user's HTML profile page
            "web": target.web
        },
        "published": timezone.now().isoformat(),
        "state": "REQUESTED",
    }
    
    print(f"[DEBUG create_follow_activity] Activity created: id={activity_id}, type={activity['type']}, ")
    
    return activity

# def create_unfollow_activity(actor_author, target_id):
#     activity_id = make_fqid(actor_author, "undo-follow")

#     activity = {
#         "type": "Undo",
#         "id": activity_id,
#         "summary": f"{actor_author.username} stopped following you",
#         "actor": str(actor_author.id),
#         "object": {
#             "type": "Follow",
#             "actor": str(actor_author.id),
#             "object": str(target_id)
#         },
#         "published": timezone.now().isoformat(),
#     }
    
#     return activity

# def create_unfriend_activity(actor_author, target_id):
#     activity_id = make_fqid(actor_author, "unfriend")

#     activity = {
#         "type": "RemoveFriend",
#         "id": activity_id,
#         "summary": f"{actor_author.username} removed you as a friend",
#         "actor": str(actor_author.id),
#         "object": str(target_id),
#         "published": timezone.now().isoformat(),
#     }
    
#     return activity

def create_profile_update_activity(actor_author):
    activity_id = make_fqid(actor_author, "profile-update")

    activity = {
        "type": "Update",
        "id": activity_id,
        "summary": f"{actor_author.username} updated their profile",
        "actor": {
            "type": "Author",
            "id": str(actor_author.id),
            "host": actor_author.host,
            "displayName": actor_author.username,
            "github": actor_author.github,
            "profileImage": actor_author.profileImage.url if actor_author.profileImage else None ,
            "web": actor_author.web,
        },
        "object": {
            "type": "Author",
            "id": str(actor_author.id),
            "host": actor_author.host,
            "displayName": actor_author.username,
            "github": actor_author.github,
            "profileImage": actor_author.profileImage.url if actor_author.profileImage else None,
            "web": actor_author.web,
        },
        "published": timezone.now().isoformat(),
    }

    return activity

def create_unlike_activity(author, liked_object):
    activity_id = make_fqid(author, "unlike")

    activity = {
        "type": "unlike",
        "id": activity_id,
        "summary": f"{author.username} unliked an entry or comment",
        "actor": {
            "type": "Author",
            "id": str(author.id),
            "host": author.host,
            "displayName": author.username,
            "github": author.github,
            "profileImage": author.profileImage.url if author.profileImage else None,
            "web": author.web,
        },
        "published": timezone.now().isoformat(),
        "object": {
            "type": "Like",
            "id": liked_object.id,
            "author": {
                "type": "Author",
                "id": liked_object.author.id,
                "host": liked_object.author.host,
                "displayName": liked_object.author.username,
                "github": liked_object.author.github,
                "profileImage": liked_object.author.profileImage.url if liked_object.author.profileImage else None,
                "web": liked_object.author.web,
            },
            "published": liked_object.published,
            "object": liked_object.object,
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