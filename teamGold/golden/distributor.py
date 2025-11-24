import requests
from django.utils import timezone
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox
from golden.services import get_or_create_foreign_author, normalize_fqid, generate_comment_fqid, fetch_and_sync_remote_entry
from urllib.parse import urljoin
from django.conf import settings
from django.utils.dateparse import parse_datetime
from datetime import datetime as dt
import uuid

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

def safe_parse_datetime(value):
    """
    This module safely parses a datetime value and returns a datetime object or None.
    Credits: ChatGPT: "published field is not recognized as a datetime object, so we need to parse it", 11-22-2025 
    """
    if value is None:
        return None
    
    # If it's already a datetime object, return it
    if isinstance(value, dt):
        return value
    
    # If it's a string, try to parse it
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed:
            return parsed
        # If that fails, try fromisoformat (Python 3.7+)
        try:
            value_clean = value.replace('Z', '+00:00')
            return dt.fromisoformat(value_clean)
        except (ValueError, AttributeError):
            pass
    return None

def send_activity_to_inbox(recipient: Author, activity: dict):
    """Send activity to local or remote inbox."""
    print(f"[DEBUG send_activity_to_inbox] Called: recipient={recipient.username} (id={recipient.id}, host={recipient.host})")
    print(f"[DEBUG send_activity_to_inbox] Activity type: {activity.get('type')}")
    print(f"[DEBUG send_activity_to_inbox] SITE_URL: {settings.SITE_URL}")
    
    if recipient.host.rstrip("/") == settings.SITE_URL.rstrip("/"):
        # Local delivery to the inbox
        print(f"[DEBUG send_activity_to_inbox] LOCAL delivery: Creating inbox item for {recipient.username}")
        Inbox.objects.create(author=recipient, data=activity)
        print(f"[DEBUG send_activity_to_inbox] LOCAL delivery: Inbox item created successfully")
        return

    # For remote inbox, construct the URL properly
    # The inbox endpoint expects: /api/authors/<author_id>/inbox/
    # Extract the UUID or author ID part from the full FQID
    recipient_id = str(recipient.id).rstrip('/')
    
    # Extract the author ID part (UUID) from the FQID
    # FQID format: https://node.com/api/authors/{uuid}
    if '/api/authors/' in recipient_id:
        author_id_part = recipient_id.split('/api/authors/')[-1]
    else:
        # Fallback: use the last part of the URL
        author_id_part = recipient_id.split('/')[-1]
    
    # Construct inbox URL: host/api/authors/{uuid}/inbox/
    inbox_url = f"{recipient.host.rstrip('/')}/api/authors/{author_id_part}/inbox/"

    # Get node authentication if available
    from .models import Node
    from urllib.parse import urlparse
    parsed = urlparse(recipient.host)
    node_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    node = Node.objects.filter(id__startswith=node_base).first()
    auth = None
    if node and node.auth_user:
        auth = (node.auth_user, node.auth_pass)
    
    try:
        print(f"[DEBUG send_activity_to_inbox] Sending activity to {recipient.username} (id={recipient.id}, host={recipient.host})")
        print(f"[DEBUG send_activity_to_inbox] Inbox URL: {inbox_url}")
        print(f"[DEBUG send_activity_to_inbox] Activity type: {activity.get('type')}")
        print(f"[DEBUG send_activity_to_inbox] Activity: {json.dumps(activity, indent=2, default=str)}")
        
        # Ensure all datetime values are strings before JSON serialization
        def ensure_datetime_strings(obj):
            """Recursively convert datetime objects to ISO format strings"""
            if isinstance(obj, dt):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: ensure_datetime_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [ensure_datetime_strings(item) for item in obj]
            return obj
        
        activity_clean = ensure_datetime_strings(activity)
        
        response = requests.post(
            inbox_url,
            data=json.dumps(activity_clean, default=str),
            headers={"Content-Type": "application/json"},
            auth=auth,
            timeout=10,
        )
        print(f"[DEBUG send_activity_to_inbox] Response status: {response.status_code}")
        if response.status_code >= 400:
            print(f"[DEBUG send_activity_to_inbox] ERROR: HTTP {response.status_code} - {response.text}")
            raise Exception(f"Error {response.status_code}: {response.text}")
        print(f"[DEBUG send_activity_to_inbox] Successfully sent activity")
    except requests.exceptions.RequestException as e:
        print(f"[DEBUG send_activity_to_inbox] EXCEPTION: {e}")
        raise

def get_followers(author: Author):
    """Return all authors who follow this author (FOLLOW.state=ACCEPTED)."""
    # Query Follow objects directly to work with both local and remote authors
    # The object field is a URLField (FQID), so we need to normalize for matching
    author_id_normalized = normalize_fqid(str(author.id))
    follower_ids = Follow.objects.filter(
        object=author_id_normalized,
        state="ACCEPTED"
    ).values_list("actor_id", flat=True)
    
    # Also try with raw author.id in case normalization differs
    if not follower_ids:
        follower_ids = Follow.objects.filter(
            object=str(author.id).rstrip('/'),
            state="ACCEPTED"
        ).values_list("actor_id", flat=True)
    
    return Author.objects.filter(id__in=follower_ids)

def get_friends(author):
    """Mutual followers = friends."""
    # Normalize author ID for consistent matching with Follow objects
    author_id_normalized = normalize_fqid(str(author.id))
    author_id_raw = str(author.id).rstrip('/')
    
    print(f"[DEBUG get_friends] Finding friends for author: {author.username} (id={author.id})")
    
    # Get followers (people who follow this author) - actor_id is ForeignKey to Author
    # Try both normalized and raw author.id
    follower_ids_set = set()
    followers_normalized = Follow.objects.filter(
        object=author_id_normalized,
        state="ACCEPTED"
    ).values_list("actor_id", flat=True)
    followers_raw = Follow.objects.filter(
        object=author_id_raw,
        state="ACCEPTED"
    ).values_list("actor_id", flat=True)
    follower_ids_set.update(followers_normalized)
    follower_ids_set.update(followers_raw)
    
    print(f"[DEBUG get_friends] Found {len(follower_ids_set)} followers")
    
    # Get following (people this author follows) - object is URLField (FQID string)
    following_follows = Follow.objects.filter(
        actor=author,
        state="ACCEPTED"
    )
    following_ids_set = set()
    following_ids_normalized_set = set()
    for follow in following_follows:
        following_ids_set.add(follow.object)  # Raw FQID string
        following_ids_normalized_set.add(normalize_fqid(str(follow.object)))  # Normalized
    
    print(f"[DEBUG get_friends] Found {len(following_ids_set)} following")
    
    # Find mutual: authors whose ID appears in both sets
    # follower_ids_set contains Author.id values (from ForeignKey actor_id)
    # following_ids_set contains FQID strings (from URLField object)
    mutual_author_ids = []
    for follower_id in follower_ids_set:
        # follower_id is an Author.id (URLField), try both normalized and raw
        follower_id_normalized = normalize_fqid(str(follower_id))
        follower_id_raw = str(follower_id).rstrip('/')
        
        # Check if this follower is also in the following set
        # We need to check if the follower's ID (in any form) matches any following ID
        is_mutual = (
            follower_id_normalized in following_ids_normalized_set or
            follower_id_raw in following_ids_set or
            str(follower_id) in following_ids_set or
            follower_id_normalized in following_ids_set
        )
        
        if is_mutual:
            mutual_author_ids.append(follower_id)
            print(f"[DEBUG get_friends] Found mutual friend: {follower_id}")
    
    print(f"[DEBUG get_friends] Total mutual friends: {len(mutual_author_ids)}")
    
    # Return Author objects for mutual friends
    if mutual_author_ids:
        return Author.objects.filter(id__in=mutual_author_ids)
    
    return Author.objects.none()

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
        if src:
            if src.startswith("/"):
                img["src"] = urljoin(base_url.rstrip("/") + "/", src.lstrip("/"))
            elif not src.startswith("http") and not src.startswith("data:"):
                img["src"] = urljoin(base_url.rstrip("/") + "/", src)

    return str(soup)

# * ============================================================
# * Main Distributor
# * ============================================================

def distribute_activity(activity: dict, actor: Author):
    """
    Main distribution function - determines recipients and sends activities.
    It prioritizes FQID for author comparisons and activities.
    """

    type_lower = activity.get("type", "").lower()
    obj = activity.get("object")

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
        print(f"[DEBUG distribute_activity] UPDATE ENTRY: actor={actor.username} (id={actor.id})")
        print(f"[DEBUG distribute_activity] UPDATE ENTRY: entry_id={obj.get('id')}")
        print(f"[DEBUG distribute_activity] UPDATE ENTRY: title={obj.get('title')}")
        print(f"[DEBUG distribute_activity] UPDATE ENTRY: visibility={obj.get('visibility')}")
        
        visibility = obj.get("visibility", "PUBLIC").upper()
        recipients = set()

        if visibility == "PUBLIC":
            followers = get_followers(actor)
            friends = get_friends(actor)
            recipients |= set(followers)
            recipients |= set(friends)
            print(f"[DEBUG distribute_activity] UPDATE ENTRY: Found {len(followers)} followers, {len(friends)} friends")
        elif visibility == "UNLISTED":
            followers = get_followers(actor)
            recipients |= set(followers)
            print(f"[DEBUG distribute_activity] UPDATE ENTRY: Found {len(followers)} followers (UNLISTED)")
        elif visibility == "FRIENDS":
            friends = get_friends(actor)
            recipients |= set(friends)
            print(f"[DEBUG distribute_activity] UPDATE ENTRY: Found {len(friends)} friends (FRIENDS)")

        # Also send to local inbox for immediate processing on the same node
        # This ensures the update is reflected immediately on the node where it was made
        print(f"[DEBUG distribute_activity] UPDATE ENTRY: Sending to {len(recipients)} recipients + local inbox")
        send_activity_to_inbox(actor, activity)  # Send to actor's own inbox for local processing
        
        for r in recipients:
            print(f"[DEBUG distribute_activity] UPDATE ENTRY: Sending to recipient {r.username} (id={r.id}, host={r.host})")
            send_activity_to_inbox(r, activity)
        return

    # DELETE ENTRY
    if type_lower == "delete" and isinstance(obj, dict) and obj.get("type") == "post":
        recipients = set(get_followers(actor)) | set(get_friends(actor))
        for r in recipients:
            send_activity_to_inbox(r, activity)
        return

    # COMMENT 
    if type_lower == "comment":
        entry_id = None
        if isinstance(obj, str):
            entry_id = obj
        elif isinstance(obj, dict):
            entry_id = obj.get("entry")
        
        if not entry_id:
            return
        
        entry = Entry.objects.filter(id=normalize_fqid(entry_id)).first()
        if not entry:
            entry = Entry.objects.filter(id=entry_id).first()
        
        # If entry not found locally, try to extract author FQID from entry FQID or fetch entry
        if not entry:
            print(f"[DEBUG distribute_activity] COMMENT: Entry not found locally, attempting to fetch and sync: entry_id={entry_id}")
            # Try to sync the entry from remote node
            entry = fetch_and_sync_remote_entry(entry_id)
        
        if entry:
            # Distribute comment to entry author AND their followers/friends (like entry updates)
            # This ensures all nodes viewing the entry see the new comment
            print(f"[DEBUG distribute_activity] COMMENT: Found entry, author={entry.author.username} (id={entry.author.id})")
            recipients = {entry.author}
            
            # Also send to followers/friends of the entry author (like entry updates do)
            # This ensures all nodes that can see the entry also see the comment
            visibility = entry.visibility.upper() if hasattr(entry, 'visibility') else "PUBLIC"
            if visibility == "PUBLIC":
                followers = get_followers(entry.author)
                friends = get_friends(entry.author)
                recipients |= set(followers)
                recipients |= set(friends)
                print(f"[DEBUG distribute_activity] COMMENT: Adding {len(followers)} followers and {len(friends)} friends")
            elif visibility == "UNLISTED":
                followers = get_followers(entry.author)
                recipients |= set(followers)
                print(f"[DEBUG distribute_activity] COMMENT: Adding {len(followers)} followers (UNLISTED)")
            elif visibility == "FRIENDS":
                friends = get_friends(entry.author)
                recipients |= set(friends)
                print(f"[DEBUG distribute_activity] COMMENT: Adding {len(friends)} friends (FRIENDS)")
            
            print(f"[DEBUG distribute_activity] COMMENT: Sending to {len(recipients)} recipients")
            for r in recipients:
                print(f"[DEBUG distribute_activity] COMMENT: Sending to {r.username} (id={r.id}, host={r.host})")
                send_activity_to_inbox(r, activity)
        else:
            # Last resort: try to extract author from entry FQID pattern
            # Entry FQID format: https://node.com/api/authors/{author_uuid}/entries/{entry_uuid}
            # Or: https://node.com/api/entries/{entry_uuid} (need to fetch to get author)
            print(f"[DEBUG distribute_activity] COMMENT: ERROR - Could not find entry or extract author: entry_id={entry_id}")
        return

    # LIKE
    if type_lower == "like":
        liked_fqid = obj if isinstance(obj, str) else None
        if not liked_fqid:
            print(f"[DEBUG distribute_activity] LIKE: No liked_fqid in activity object")
            return

        print(f"[DEBUG distribute_activity] LIKE: Processing like for liked_fqid={liked_fqid}, actor={actor.username}")

        # Attempts to find entry locally with normalization
        entry = Entry.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not entry:
            entry = Entry.objects.filter(id=liked_fqid).first()
        
        # Attempts to find comment locally
        comment = Comment.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not comment:
            comment = Comment.objects.filter(id=liked_fqid).first()

        recipients = set()
        
        if entry:
            print(f"[DEBUG distribute_activity] LIKE: Found entry locally, author={entry.author.username} (id={entry.author.id}, host={entry.author.host})")
            recipients.add(entry.author)
            
            # Also send to followers/friends of the entry author (like entry updates do)
            # This ensures all nodes that can see the entry also see the like update
            visibility = entry.visibility.upper() if hasattr(entry, 'visibility') else "PUBLIC"
            if visibility == "PUBLIC":
                followers = get_followers(entry.author)
                friends = get_friends(entry.author)
                recipients |= set(followers)
                recipients |= set(friends)
                print(f"[DEBUG distribute_activity] LIKE: Adding {len(followers)} followers and {len(friends)} friends")
            elif visibility == "UNLISTED":
                followers = get_followers(entry.author)
                recipients |= set(followers)
                print(f"[DEBUG distribute_activity] LIKE: Adding {len(followers)} followers (UNLISTED)")
            elif visibility == "FRIENDS":
                friends = get_friends(entry.author)
                recipients |= set(friends)
                print(f"[DEBUG distribute_activity] LIKE: Adding {len(friends)} friends (FRIENDS)")
        elif comment:
            print(f"[DEBUG distribute_activity] LIKE: Found comment locally, author={comment.author.username} (id={comment.author.id}, host={comment.author.host})")
            recipients.add(comment.author)
            
            # Also send to followers/friends of the comment author
            followers = get_followers(comment.author)
            friends = get_friends(comment.author)
            recipients |= set(followers)
            recipients |= set(friends)
            print(f"[DEBUG distribute_activity] LIKE: Adding {len(followers)} followers and {len(friends)} friends for comment")
        else:
            # Entry/comment not found locally - try to sync from remote
            print(f"[DEBUG distribute_activity] LIKE: Entry/comment not found locally, attempting to fetch and sync: liked_fqid={liked_fqid}")
            entry = fetch_and_sync_remote_entry(liked_fqid)
            if entry:
                print(f"[DEBUG distribute_activity] LIKE: Successfully synced entry, author={entry.author.username} (id={entry.author.id}, host={entry.author.host})")
                recipients.add(entry.author)
                
                # Also send to followers/friends of the entry author
                visibility = entry.visibility.upper() if hasattr(entry, 'visibility') else "PUBLIC"
                if visibility == "PUBLIC":
                    followers = get_followers(entry.author)
                    friends = get_friends(entry.author)
                    recipients |= set(followers)
                    recipients |= set(friends)
                    print(f"[DEBUG distribute_activity] LIKE: Adding {len(followers)} followers and {len(friends)} friends")
                elif visibility == "UNLISTED":
                    followers = get_followers(entry.author)
                    recipients |= set(followers)
                    print(f"[DEBUG distribute_activity] LIKE: Adding {len(followers)} followers (UNLISTED)")
                elif visibility == "FRIENDS":
                    friends = get_friends(entry.author)
                    recipients |= set(friends)
                    print(f"[DEBUG distribute_activity] LIKE: Adding {len(friends)} friends (FRIENDS)")
            else:
                # Try to extract author from FQID pattern
                # Entry FQID: https://node.com/api/authors/{author_uuid}/entries/{entry_uuid}
                if '/api/authors/' in liked_fqid and '/entries/' in liked_fqid:
                    # Extract author FQID from entry FQID
                    author_fqid = '/api/authors/'.join(liked_fqid.split('/api/authors/')[:2]).split('/entries/')[0]
                    print(f"[DEBUG distribute_activity] LIKE: Extracting author from FQID: {author_fqid}")
                    author = get_or_create_foreign_author(author_fqid)
                    if author:
                        print(f"[DEBUG distribute_activity] LIKE: Extracted author={author.username} (id={author.id}, host={author.host})")
                        recipients.add(author)
                else:
                    print(f"[DEBUG distribute_activity] LIKE: ERROR - Could not find entry/comment or extract author for like: liked_fqid={liked_fqid}")

        print(f"[DEBUG distribute_activity] LIKE: Sending to {len(recipients)} recipients")
        for r in recipients:
            print(f"[DEBUG distribute_activity] LIKE: Sending like activity to {r.username} (id={r.id}, host={r.host})")
            send_activity_to_inbox(r, activity)
        return

    # UNLIKE handle "undo" (ActivityPub) formats
    if type_lower == "unlike":
        liked_fqid = obj if isinstance(obj, str) else None
        if not liked_fqid:
            return

        # Try to find entry locally (with normalization)
        entry = Entry.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not entry:
            entry = Entry.objects.filter(id=liked_fqid).first()
        
        # Try to find comment locally
        comment = Comment.objects.filter(id=normalize_fqid(liked_fqid)).first()
        if not comment:
            comment = Comment.objects.filter(id=liked_fqid).first()

        recipients = set()
        
        if entry:
            print(f"[DEBUG distribute_activity] UNLIKE: Found entry locally, author={entry.author.username} (id={entry.author.id}, host={entry.author.host})")
            recipients.add(entry.author)
            # Also send to followers/friends of the entry author
            visibility = entry.visibility.upper() if hasattr(entry, 'visibility') else "PUBLIC"
            if visibility == "PUBLIC":
                followers = get_followers(entry.author)
                friends = get_friends(entry.author)
                recipients |= set(followers)
                recipients |= set(friends)
                print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(followers)} followers and {len(friends)} friends")
            elif visibility == "UNLISTED":
                followers = get_followers(entry.author)
                recipients |= set(followers)
                print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(followers)} followers (UNLISTED)")
            elif visibility == "FRIENDS":
                friends = get_friends(entry.author)
                recipients |= set(friends)
                print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(friends)} friends (FRIENDS)")
        elif comment:
            print(f"[DEBUG distribute_activity] UNLIKE: Found comment locally, author={comment.author.username} (id={comment.author.id}, host={comment.author.host})")
            recipients.add(comment.author)
            # Also send to followers/friends of the comment author
            followers = get_followers(comment.author)
            friends = get_friends(comment.author)
            recipients |= set(followers)
            recipients |= set(friends)
            print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(followers)} followers and {len(friends)} friends for comment")
        else:
            # Entry/comment not found locally - try to sync from remote
            print(f"[DEBUG distribute_activity] UNLIKE: Entry/comment not found locally, attempting to fetch and sync: liked_fqid={liked_fqid}")
            entry = fetch_and_sync_remote_entry(liked_fqid)
            if entry:
                print(f"[DEBUG distribute_activity] UNLIKE: Successfully synced entry, author={entry.author.username} (id={entry.author.id}, host={entry.author.host})")
                recipients.add(entry.author)
                # Also send to followers/friends
                visibility = entry.visibility.upper() if hasattr(entry, 'visibility') else "PUBLIC"
                if visibility == "PUBLIC":
                    followers = get_followers(entry.author)
                    friends = get_friends(entry.author)
                    recipients |= set(followers)
                    recipients |= set(friends)
                    print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(followers)} followers and {len(friends)} friends")
                elif visibility == "UNLISTED":
                    followers = get_followers(entry.author)
                    recipients |= set(followers)
                    print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(followers)} followers (UNLISTED)")
                elif visibility == "FRIENDS":
                    friends = get_friends(entry.author)
                    recipients |= set(friends)
                    print(f"[DEBUG distribute_activity] UNLIKE: Adding {len(friends)} friends (FRIENDS)")
            else:
                # Try to extract author from FQID pattern
                if '/api/authors/' in liked_fqid and '/entries/' in liked_fqid:
                    author_fqid = '/api/authors/'.join(liked_fqid.split('/api/authors/')[:2]).split('/entries/')[0]
                    print(f"[DEBUG distribute_activity] UNLIKE: Extracting author from FQID: {author_fqid}")
                    author = get_or_create_foreign_author(author_fqid)
                    if author:
                        print(f"[DEBUG distribute_activity] UNLIKE: Extracted author={author.username} (id={author.id}, host={author.host})")
                        recipients.add(author)
                else:
                    print(f"[DEBUG distribute_activity] UNLIKE: ERROR - Could not find entry/comment or extract author: liked_fqid={liked_fqid}")

        print(f"[DEBUG distribute_activity] UNLIKE: Sending to {len(recipients)} recipients")
        for r in recipients:
            print(f"[DEBUG distribute_activity] UNLIKE: Sending unlike activity to {r.username} (id={r.id}, host={r.host})")
            send_activity_to_inbox(r, activity)
        return
    
    # UNLIKE (ActivityPub format - keep for backward compatibility)
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
        target_id = obj.get("id")
        print(f"[DEBUG distribute_activity] FOLLOW: Processing follow activity")
        print(f"[DEBUG distribute_activity] FOLLOW: actor={actor.username} (id={actor.id})")
        print(f"[DEBUG distribute_activity] FOLLOW: target_id (raw)={target_id}")
        
        target_id_normalized = normalize_fqid(target_id)
        print(f"[DEBUG distribute_activity] FOLLOW: target_id (normalized)={target_id_normalized}")
        
        target = Author.objects.filter(id=target_id_normalized).first()
        print(f"[DEBUG distribute_activity] FOLLOW: Lookup by normalized FQID: target={target.username if target else 'None'} (id={target.id if target else 'None'})")

        # If target doesn't exist locally by FQID, try to get/create
        if not target:
            print(f"[DEBUG distribute_activity] FOLLOW: Target not found, calling get_or_create_foreign_author")
            target = get_or_create_foreign_author(target_id)
            print(f"[DEBUG distribute_activity] FOLLOW: get_or_create_foreign_author returned: target={target.username if target else 'None'} (id={target.id if target else 'None'})")
        
        if target:
            print(f"[DEBUG distribute_activity] FOLLOW: Sending activity to target inbox: target={target.username} (id={target.id}, host={target.host})")
            send_activity_to_inbox(target, activity)
            print(f"[DEBUG distribute_activity] FOLLOW: Activity sent successfully")
        else:
            print(f"[DEBUG distribute_activity] FOLLOW: ERROR - Target is None, cannot send activity")
        return

    """
    # ACCEPT or REJECT
    if type_lower == "accept" or type_lower == "reject":
        follow_obj = obj or {}

        if isinstance(follow_obj, dict):
            follower_id = follow_obj.get("actor") # Who made the follow request
            target = Author.objects.filter(id=normalize_fqid(follow_obj.get("object"))).first()

            if not target and follower_id:
                target = get_or_create_foreign_author(follower_id)
        elif isinstance(follow_obj, str):
            # If it's a Follow ID string, look it up
            follow = Follow.objects.filter(id=follow_obj).first()
            if follow:
                target = follow.actor
                # If actor doesn't exist (shouldn't happen, but be safe)
                if not target:
                    target = get_or_create_foreign_author(follow.actor.username if hasattr(follow, 'actor') else follow.actor_id)
            else:
                target = None
        
        if target:
            send_activity_to_inbox(target, activity)
       
        return
        """

    # UNFOLLOW
    if type_lower == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "follow":
        target_id = obj.get("object")
        target = Author.objects.filter(id=normalize_fqid(target_id)).first()

        if target:
            send_activity_to_inbox(target, activity)
        return

    # REMOVE FRIEND
    if type_lower == "removefriend":
        target_id = obj
        target = Author.objects.filter(id=normalize_fqid(target_id)).first()

        if target:
            send_activity_to_inbox(target, activity)
        return

# * ============================================================
# * Inbox Processor
# * ============================================================

def process_inbox(author: Author):
    inbox_items = Inbox.objects.filter(author=author, processed=False)

    for item in inbox_items:
        activity = item.data
        activity_type = activity.get("type", "").lower()
        obj = activity.get("object")

        actor_data = activity.get("actor")
        actor_id = None
        actor_username = None
        actor_host = None
        
        if isinstance(actor_data, dict):
            actor_id = actor_data.get("id") or actor_data.get("@id")
            actor_username = actor_data.get("username") or actor_data.get("displayName")
            actor_host = actor_data.get("host")
        elif isinstance(actor_data, str):
            actor_id = actor_data
        
        actor = None
        if actor_id:
            actor = Author.objects.filter(id=normalize_fqid(actor_id)).first()
            if not actor:
                actor = get_or_create_foreign_author(
                    actor_id,
                    host=actor_host,
                    username=actor_username
                )

        # FOLLOW REQUEST
        if activity_type == "follow":
            follower = actor
            target_id_raw = obj.get("id")
            target_id = normalize_fqid(target_id_raw)
            
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: Processing Follow activity")
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: follower={follower.username if follower else 'None'} (id: {actor_id})")
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: target_id (raw)='{obj}'")
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: target_id (normalized)='{target_id}'")
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: inbox author (being followed)={author.username} (id: {author.id})")
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: activity_id={activity.get('id')}")
            print(f"[DEBUG process_inbox] FOLLOW REQUEST: activity={json.dumps(activity, indent=2, default=str)}")
            
            if follower and target_id:
                author_id_normalized = normalize_fqid(str(author.id))
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: author_id_normalized={author_id_normalized}")
                if target_id != author_id_normalized:
                    print(f"[DEBUG process_inbox] FOLLOW REQUEST: WARNING - target_id mismatch, using inbox author ID")
            
                    target_id = author_id_normalized
                
                # Delete any existing follow request
                existing = Follow.objects.filter(actor=follower, object=target_id)
                existing_count = existing.count()
                existing.delete()
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: Deleted {existing_count} existing follow requests")

                follow_id = f"{actor.id.rstrip('/')}/{suffix}/{uuid.uuid4()}"
                follow_obj = Follow.objects.create(
                    #id=activity.get("id"),
                    id = follow_id,
                    actor=follower,
                    object=target_id,
                    state="REQUESTED",
                    summary=activity.get("summary", ""),
                    published=safe_parse_datetime(activity.get("published")) or timezone.now()
                )
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: Created Follow object")
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: follow_obj.id={follow_obj.id}")
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: follow_obj.actor={follow_obj.actor.username} (id={follow_obj.actor.id})")
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: follow_obj.object={follow_obj.object}")
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: follow_obj.state={follow_obj.state}")
                
                item.processed = True
                item.save()
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: Marked inbox item {item.id} as processed")
           
            else:
                print(f"[DEBUG process_inbox] FOLLOW REQUEST: ERROR - follower={follower}, target_id={target_id}")

        # ACCEPT FOLLOW
        elif activity_type == "accept":
            follow_obj = obj or {}
            processed = False
            
            if isinstance(follow_obj, str):
                follow = Follow.objects.filter(id=follow_obj).first()
                if follow:
                    follow.state = "ACCEPTED"
                    follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                    follow.save()
                    
                    follower = follow.actor
                    target = Author.objects.filter(id=follow.object).first()
                    if follower and target:
                        follower.following.add(target)
                        processed = True
            
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
                        follow = Follow.objects.filter(actor=follower, object=target_id).first()
                        if follow:
                            follow.state = "ACCEPTED"
                            follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                            follow.save()
                        else:
                            follow_id = activity.get("object") if isinstance(activity.get("object"), str) else None
                            if not follow_id:
                                follow_id = f"{follower.id}/follow/{uuid.uuid4()}"
                            
                            Follow.objects.create(
                                id=follow_id,
                                actor=follower,
                                object=target_id,
                                state="ACCEPTED",
                                summary=activity.get("summary", ""),
                                published=safe_parse_datetime(activity.get("published")) or timezone.now()
                            )
                        
                        follower.following.add(target)
                        processed = True
            
        # REJECT FOLLOW
        elif activity_type == "reject":
            follow_obj = obj or {}
            
            if isinstance(follow_obj, str):
                follow = Follow.objects.filter(id=follow_obj).first()
                if follow:
                    follow.state = "REJECTED"
                    follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                    follow.save()
            else:
                follower_id = follow_obj.get("actor")
                target_id = follow_obj.get("object")

                follower = Author.objects.filter(id=follower_id).first()
                target = Author.objects.filter(id=target_id).first()

                if follower and target:
                    follow = Follow.objects.filter(actor=follower, object=target_id).first()
                    if follow:
                        follow.state = "REJECTED"
                        follow.published = safe_parse_datetime(activity.get("published")) or timezone.now()
                        follow.save()
                    else:
                        Follow.objects.create(
                            id=activity.get("id") or f"{follower.id}/follow/{uuid.uuid4()}",
                            actor=follower,
                            object=target_id,
                            state="REJECTED",
                            summary=activity.get("summary", ""),
                            published=safe_parse_datetime(activity.get("published")) or timezone.now()
                        )

        # UNFOLLOW
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "follow":
            follower_id = obj.get("actor")
            target_id = obj.get("object")

            follower = Author.objects.filter(id=follower_id).first()
            target = Author.objects.filter(id=target_id).first()

            if follower and target:
                Follow.objects.filter(actor=follower, object=target_id).delete()
                follower.following.remove(target)

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

        # CREATE ENTRY
        elif activity_type == "create" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")

            entry, created = Entry.objects.update_or_create(
                id=entry_id,
                defaults={
                    "title": obj.get("title", ""),
                    "description": "",
                    "content": obj.get("content", ""),
                    "contentType": obj.get("contentType", "text/plain"),
                    "author": actor or author,
                    "visibility": obj.get("visibility", "PUBLIC"),
                    "published": safe_parse_datetime(obj.get("published")) or timezone.now(),
                }
            )
          
            attachments = obj.get("attachments", []) 

        # UPDATE ENTRY
        elif activity_type == "update" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")
            print(f"[DEBUG process_inbox] UPDATE ENTRY: Processing update for entry_id={entry_id}")
            print(f"[DEBUG process_inbox] UPDATE ENTRY: actor={actor.username if actor else 'None'} (id={actor.id if actor else 'None'})")
            print(f"[DEBUG process_inbox] UPDATE ENTRY: inbox author={author.username} (id={author.id})")
            
            entry = Entry.objects.filter(id=entry_id).first()
            print(f"[DEBUG process_inbox] UPDATE ENTRY: Entry lookup result: {'Found' if entry else 'NOT FOUND'}")

            if entry:
                old_title = entry.title
                old_content = entry.content[:50] if entry.content else ""
                raw_content = obj.get("content", entry.content) or entry.content
                base_url = getattr(actor, "host", "") if actor else ""
                content = absolutize_remote_images(raw_content, base_url)

                entry.title = obj.get("title", entry.title)
                entry.content = content
                entry.contentType = obj.get("contentType", entry.contentType)
                entry.visibility = obj.get("visibility", entry.visibility)
                entry.save()
                print(f"[DEBUG process_inbox] UPDATE ENTRY: Updated entry {entry_id}")
                print(f"[DEBUG process_inbox] UPDATE ENTRY: Title changed from '{old_title}' to '{entry.title}'")
                print(f"[DEBUG process_inbox] UPDATE ENTRY: Content length: {len(old_content)} -> {len(entry.content)}")
            else:
                print(f"[DEBUG process_inbox] UPDATE ENTRY: ERROR - Entry {entry_id} not found in database!")

        # DELETE ENTRY
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "post":
            entry_id = obj.get("id")
            entry = Entry.objects.filter(id=entry_id).first()
            if entry:
                entry.visibility = "DELETED"
                entry.save()

        # COMMENT
        elif activity_type == "comment":
            comment_id = activity.get("id")  
            entry_id = None
            comment_content = None
            comment_content_type = None
            comment_author_id = None
            
            if isinstance(obj, str):
                entry_id = obj
                comment_content = activity.get("comment", "")
                comment_content_type = activity.get("contentType", "text/plain")
                author_data = activity.get("author")
                if isinstance(author_data, dict):
                    comment_author_id = author_data.get("id")
                elif isinstance(author_data, str):
                    comment_author_id = author_data
            elif isinstance(obj, dict):
                entry_id = obj.get("entry")
                comment_content = obj.get("content", "")
                comment_content_type = obj.get("contentType", "text/plain")
                comment_author_id = obj.get("author")
                if not comment_id:
                    comment_id = obj.get("id")
            
            if not entry_id:
                return
            
            entry = Entry.objects.filter(id=normalize_fqid(entry_id)).first()
            if not entry:
                entry = Entry.objects.filter(id=entry_id).first()
            
            if entry:
                comment_author = None
                if comment_author_id:
                    if isinstance(comment_author_id, dict):
                        comment_author_id = comment_author_id.get("id")
                    comment_author = Author.objects.filter(id=normalize_fqid(comment_author_id)).first()
                    if not comment_author:
                        # Extract username from author object if available
                        author_obj = activity.get("author") if isinstance(activity.get("author"), dict) else None
                        username = author_obj.get("username") or author_obj.get("displayName") if author_obj else None
                        host = author_obj.get("host") if author_obj else None
                        comment_author = get_or_create_foreign_author(comment_author_id, host=host, username=username)
                
                if not comment_author:
                    comment_author = actor 
                
                if not comment_id:
                    comment_id = generate_comment_fqid(comment_author, entry)
                
                Comment.objects.update_or_create(
                    id=comment_id,
                    defaults={
                        "entry": entry,
                        "author": comment_author,
                        "content": comment_content or "",
                        "contentType": comment_content_type or "text/plain",
                        "published": safe_parse_datetime(activity.get("published")) or timezone.now()
                    }
                )

        # DELETE COMMENT
        elif activity_type == "delete" and isinstance(obj, dict) and obj.get("type") == "comment":
            Comment.objects.filter(id=obj.get("id")).delete()

        # LIKE
        elif activity_type == "like":
            obj_id = activity.get("object")

            Like.objects.filter(author=actor, object=obj_id).delete()
            
            like = Like.objects.create(
                id=activity.get("id"),
                author=actor,
                object=obj_id,
                published=safe_parse_datetime(activity.get("published")) or timezone.now()
            )
            
            entry = Entry.objects.filter(id=obj_id).first()
            if entry:
                entry.likes.add(actor)

        # UNLIKE
        elif activity_type == "unlike":
            obj_id = obj if isinstance(obj, str) else None
            actor_id = activity.get("actor")
            
            if not obj_id:
                return
            
            like_actor = Author.objects.filter(id=actor_id).first()
            if not like_actor and actor_id:
                like_actor = get_or_create_foreign_author(actor_id)
            
            if like_actor:
                Like.objects.filter(author=like_actor, object=obj_id).delete()
                
                entry = Entry.objects.filter(id=obj_id).first()
                if entry:
                    entry.likes.remove(like_actor)
                        
        # UNLIKE (ActivityPub format - keep for backward compatibility)
        elif activity_type == "undo" and isinstance(obj, dict) and obj.get("type", "").lower() == "like":
            obj_id = obj.get("object")
            actor_id = obj.get("actor")
            
            like_actor = Author.objects.filter(id=actor_id).first()
            if not like_actor and actor_id:
                like_actor = get_or_create_foreign_author(actor_id)
            
            if like_actor:
                Like.objects.filter(author=like_actor, object=obj_id).delete()
                
                entry = Entry.objects.filter(id=obj_id).first()
                if entry:
                    entry.likes.remove(like_actor)
                

        # Mark as processed after successful processing
        # Processed variable is only set for ACCEPT, so check activity_type for others
        if activity_type in ["follow", "accept", "reject", "unlike", "undo", "removefriend", "create", "update", "delete", "comment", "like"]:
            item.processed = True
            item.save()
