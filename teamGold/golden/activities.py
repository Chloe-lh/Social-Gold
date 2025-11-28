import uuid
from django.utils import timezone
from django.conf import settings
from urllib.parse import urlparse
from golden.models import Follow
import requests
from django.conf import settings

node_url = settings.SITE_URL

# this function needs to be moved to services
def make_fqid(author, suffix: str):
    """
    Example:
      author.id = https://yoursite/api/authors/<uuid>
      return =   https://yoursite/api/authors/<uuid>/<suffix>/<uuid>
    """
    return f"{author.id.rstrip('/')}/{suffix}/{uuid.uuid4()}"

# this function needs to be moved to services
def is_local(author_id):
    """
    Determines if the given author_id belongs to a local author or a remote one.
    Compares the host portion of the author_id URL with the current site's host.
    """
    author_host = urlparse(author_id).netloc
    site_host = urlparse(settings.SITE_URL).netloc
    return author_host == site_host

# * ============================================================
# * Entry / Comment / Like Activities
# * ============================================================

def create_new_entry_activity(author, entry):
    activity_id = make_fqid(author, "posts")

    commentList = get_comment_list_api(entry.id)
    likeList = get_like_api(entry.id)
    activity = {
        "type": "Entry",
        "title" : entry.title,
        "id": entry.id,
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
        "id": entry.id,
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
    #activity_id = make_fqid(author, "posts")
    commentList = get_comment_list_api(entry.id)
    likeList = get_like_api(entry.id)
   
    activity = {
        "type": "Entry",
        "title" : entry.title,
        "id": entry.id,
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
    #activity_id = make_fqid(author, "comments")
    activity = {
        "type": "comment",
        "author":{
            "type":"author",
            "id":author.id,
            "web":author.web,
            "host":author.host,
            "displayName":author.username,
            "github":author.github,
            "profileImage":author.profileImage.url if author.profileImage else None,
        },
        "comment":comment.content,
        "contentType":comment.contentType,
        "published":comment.published,
        "id":comment.id,
        "entry":entry.id,
        "likes":{},
    }
    return activity

def create_like_activity(author, like_obj):
    #activity_id = make_fqid(author, "likes")

    activity = {
        "type": "like",
        "id":activity_id,
        "author":{
            "type":"author",
            "id":author.id,
            "web":author.web,
            "host":author.host,
            "displayName":author.username,
            "github":author.github,
            "profileImage":author.profileImage.url if author.profileImage else None
        },
        "published":timezone.now().isoformat(),
        "id":like_obj.id,
        "object":like_obj.object,
    }
    return activity

def create_unlike_activity(author, liked_object_fqid):
    activity_id = make_fqid(author, "unlike")

    activity = {
        "type": "unlike",
        "id": activity_id,
        "author": {
            "type": "author",
            "id": author.id,
            "web": author.web,
            "host": author.host,
            "displayName": author.name,
            "github": author.github,
            "profileImage":author.profileImage.url if author.profileImage else None
        },
        "published": timezone.now().isoformat(),
        "object": liked_object_fqid,
    }

    return activity

# * ============================================================
# * Author-Related Activities
# * ============================================================

def create_follow_activity(author, target):
    """
    Creates a follow activity when author wants to follow target.
    Format matches ActivityPub specification.
    """
    activity_id = make_fqid(author, "follow")
    
    print(f"[DEBUG create_follow_activity] Creating follow activity: actor={author.username} (id={author.id}), target={target.username} (id={target.id})")
    
    activity = {
        "type":"follow",
        "summary":f"{author.username} wants to follow {target.username}",
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
        "object":{
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

# * ============================================================
# * Helper Functions
# * ============================================================

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
'''  
def get_comment_list_api(entry_id):
    """Get comments for an entry - query database directly"""
    from golden.models import Comment
    from golden.services import normalize_fqid
    
    # Normalize the entry ID to handle different FQID formats
    entry_id_normalized = normalize_fqid(entry_id)
    
    # Query the database directly - no HTTP requests!
    try:
        comments = Comment.objects.filter(
            entry_id=entry_id_normalized
        ).select_related('author').order_by('-published')
        
        # Return in the same format your API would return
        comment_list = []
        for comment in comments:
            comment_list.append({
                "type": "comment",
                "id": str(comment.id),
                "author": {
                    "type": "author",
                    "id": str(comment.author.id),
                    "host": comment.author.host,
                    "displayName": comment.author.username,
                    "github": comment.author.github,
                    "profileImage": comment.author.profileImage.url if comment.author.profileImage else None,
                    "web": comment.author.web,
                },
                "comment": comment.content,
                "contentType": comment.contentType,
                "published": comment.published.isoformat() if comment.published else None,
            })
        
        return comment_list
    except Exception as e:
        print(f"Error fetching comment list for entry {entry_id}:", e)
        return []


def get_like_api(like_id):
    """Get likes for an entry - query database directly"""
    from golden.models import Like, Entry
    from golden.services import normalize_fqid
    
    # If like_id is actually an entry_id, get all likes for that entry
    entry_id_normalized = normalize_fqid(like_id)
    
    try:
        # Get all likes for this entry
        entry = Entry.objects.filter(id=entry_id_normalized).first()
        
        if not entry:
            return []
        
        # Return list of authors who liked this entry
        like_list = []
        for author in entry.likes.all():
            like_list.append({
                "type": "author",
                "id": str(author.id),
                "host": author.host,
                "displayName": author.username,
                "github": author.github,
                "profileImage": author.profileImage.url if author.profileImage else None,
                "web": author.web,
            })
        
        return like_list
    except Exception as e:
        print(f"Error fetching likes for entry {like_id}:", e)
        return []

'''
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
'''  