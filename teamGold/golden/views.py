# IMPORT Standard Python
import json
import random
import uuid
from urllib.parse import urljoin, urlparse

# IMPORT RESTfuls
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# IMPORT Django  
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import (HttpResponseBadRequest, HttpResponseForbidden, JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.edit import FormView
from django.utils import timezone as dj_timezone

# IMPORT Django Local
from .decorators import require_author
from .forms import CommentForm, CustomUserForm, EntryForm, ProfileForm

# IMPORT Golden 
from golden.distributor import distribute_activity, process_inbox, get_followers, get_friends
from golden.models import (Author, Comment, Entry, EntryImage, Follow, Like, Node, Inbox)
from golden.serializers import *
from golden.services import *
from golden.services import get_or_create_foreign_author, fqid_to_uuid, is_local, normalize_fqid
from golden.activities import ( # Kenneth: If you're adding new activities, please make sure they are uploaded here 
    create_comment_activity,
    create_delete_entry_activity,
    create_follow_activity,
    create_like_activity,
    create_new_entry_activity,
    create_update_entry_activity,
    create_unlike_activity,
    create_profile_update_activity,
)

# IMPORT Miscellaneous
import bleach
import markdown
import requests
import markdownify

# * ============================================================
# * Direct Security Utility 
# * ============================================================

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'title'],
    'div': ['class'],
    'span': ['class'],
    'code': ['class'],
}

# ChatGPT: please verify add and verify all HTML Tags, 11-21-2025
ALLOWED_TAGS = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'strong', 'em', 'u',
    'blockquote', 'code', 'pre', 'hr',
    'ul', 'ol', 'li',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span',
]

def sanitize_html(content):
    if not content:
        return ""
    
    cleaned = bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )
    return cleaned

def sanitize_markdown_to_html(markdown_content):
    """
    Convert markdown to HTML and sanitize it.
    """
    if not markdown_content:
        return ""
    
    # Convert markdown to HTML
    html_content = markdown.markdown(markdown_content)
    
    # Sanitize the HTML
    return sanitize_html(html_content)

def html_to_markdown(html_content):
    """
    Convert html to markdown
    """
    return markdownify.markdownify(html_content)

def validate_url(url):
    if not url:
        return True
    
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https', '']:
            return False
        return True
    except Exception:
        return False

def validate_visibility(visibility):
    return visibility in ['PUBLIC', 'UNLISTED', 'FRIENDS', 'DELETED']

# * ============================================================
# * View Helper Classes
# * ============================================================

class CustomLoginView(LoginView):
    '''
    For displaying an error message if a user is not approved yet
    '''
    def form_valid(self, form):
        user = form.get_user()
        if not getattr(user, 'is_approved'):
            form.add_error(None, "user has not been approved yet")
            return self.form_invalid(form)
        else:
            return super().form_valid(form)
        
class ApprovedUserBackend(ModelBackend):
    '''
    Uses the database to authenticate if a user is approved or not
    Uses Djangos Authentication Backend and will allow user to log in if approved
    '''
    def user_can_authenticate(self, user):
        is_approved = getattr(user, 'is_approved')
        if isinstance(user, Author) and is_approved:
            return super().user_can_authenticate(user)
        return False # dont allow user to log in if not approved

# * ============================================================
# * View Functions
# * ============================================================

def signup(request):
    # we want to log users out when they want to sign up
    logout(request)

    if request.method == "POST":
        # create a form instance and populate it with data from the request
        form = CustomUserForm(request.POST)
        
        # we don't want to create a user if the inputs are not valid since that can raise errors
        if form.is_valid():
            user = form.save(commit=False)
            user.save()
            return redirect('profile')     
    else:
        form = CustomUserForm()

    return render(request, "signup.html", {"form": form})

@login_required
def stream_view(request):
    """
    Primary view to see all entries and their filtered variations 
    """
    # current user as Author
    user_author = Author.from_user(request.user)
    if not user_author:
        return redirect('login')
    process_inbox(user_author)
    #following
    #follows = Follow.objects.filter(actor=user_author, state='ACCEPTED')
    #followed_author_fqids = [f.object for f in follows]

    #use set intersection using the author's followings to get this part
    
    '''
    for f in follows:
        try:
            reciprocal = Follow.objects.get(
                actor__id=f.object,
                object=user_author.id,
                state='ACCEPTED'
            )
            friends_fqids.append(f.object)
        except Follow.DoesNotExist:     
            continue
            '''
    #people following the user
    followers_qs = Author.objects.filter(following=user_author)
    #people user is following
    following_qs = Author.objects.filter(followers_set=user_author)

    followers = followers_qs.values_list("id", flat=True)
    following = following_qs.values_list("id", flat=True)

    friends = followers_qs.intersection(following_qs).values_list("id", flat=True)

    remote_entries = []
    remote_nodes = Node.objects.filter(is_active=True)
    for node in remote_nodes:

        raw_items = fetch_remote_entries(node) or []

        for item in raw_items:
            author_data = item.get("author", {})
            remote_author_id = author_data.get("id")
            #hm?
            entry_visibility = item.get("visibility", "PUBLIC").upper()

            if not remote_author_id:
                continue

            # Check if user follows this author (for UNLISTED and FRIENDS entries)
            if remote_author_id in following:
             is_following = True
            else:
                is_following = False
            '''
            Follow.objects.filter(
                actor=user_author, 
                object=remote_author_id, 
                state="ACCEPTED"
            ).exists()
            '''
            # Check if user is friends with this author (for FRIENDS entries)
            # Friends = mutual follows (both follow each other)

            is_friend = False
            if remote_author_id in friends:
                is_friend =  True
            else:
                is_friend =  False

            '''
            if is_following:
                # Check if the remote author also follows the user (mutual follow)

                is_friend = Follow.objects.filter(
                    actor__id=remote_author_id,
                    object=user_author.id,
                    state="ACCEPTED"
                ).exists()
            '''
            should_fetch = False
            if entry_visibility == "PUBLIC":
                should_fetch = True
            elif entry_visibility == "UNLISTED" and is_following:
                should_fetch = True
            elif entry_visibility == "FRIENDS" and is_friend:
                should_fetch = True
            
            if not should_fetch:
                continue

            entry = sync_remote_entry(item, node)
            if entry:
                remote_entries.append(entry)

    local_entries = Entry.objects.filter(
        (Q(author=user_author) & ~Q(visibility="DELETED")) |
        Q(visibility='PUBLIC') |
        Q(visibility='UNLISTED', author__id__in=following) |
        Q(visibility='FRIENDS', author__id__in=friends)
    )
    visible_remote = []

    for e in remote_entries:
        # Double-check visibility (entries were pre-filtered, but verify)
        if e.visibility == "PUBLIC":
            visible_remote.append(e)
            continue

        if e.visibility == "UNLISTED":
            # UNLISTED: only visible to followers

            if e.author_id in following:
                is_following = True
            else:
                is_following = False
            '''
            is_following = Follow.objects.filter(
                actor=user_author, 
                object=e.author.id, 
                state="ACCEPTED"
            ).exists()
            '''
            if is_following:
                visible_remote.append(e)
            continue

        if e.visibility == "FRIENDS":
            # FRIENDS: only visible to mutual follows (friends)
            # Check both directions: user follows author AND author follows user
            
            friends = False
            if e.author_id in friends:
                friends =  True
            else:
                friends =  False
            '''
            user_follows_author = Follow.objects.filter(
                actor=user_author, 
                object=e.author.id, 
                state="ACCEPTED"
            ).exists()
            
            author_follows_user = False
            if user_follows_author:
                author_follows_user = Follow.objects.filter(
                    actor=e.author,
                    object=user_author.id,
                    state="ACCEPTED"
                ).exists()
            
                # Also try with author ID as string if author is a remote Author object
                if not author_follows_user:
                    author_follows_user = Follow.objects.filter(
                        actor__id=e.author.id,
                        object=user_author.id,
                        state="ACCEPTED"
                    ).exists()
            '''
            #is_mutual = user_follows_author and author_follows_user
            if friends:
                visible_remote.append(e)
            continue

    entries = list(local_entries) + visible_remote
    entries.sort(key=lambda x: x.is_posted, reverse=True)
    
    entry_authors = {entry.author for entry in entries if entry.author}

    for entry_author in entry_authors:
        if entry_author and not is_local(entry_author.id):
            
            updated_author = get_or_create_foreign_author(entry_author.id)
            
            if updated_author and updated_author.username != entry_author.username:
                entry_author.username = updated_author.username

        process_inbox(entry_author)

    context = {
        'entries': entries,
        'user_author': user_author,
        'followed_author_fqids': following,
        'friends_fqids': friends,
        'comment_form': CommentForm(),
        'remote_node': remote_nodes,
    }

    return render(request, 'stream.html', context)

@login_required
@require_author
def new_edit_entry_view(request):
    """
    Primary view to create and edit entries (with optional multiple images).
    Restores:
      - editing mode
      - removing existing images
      - adding new images
    """

    if request.current_author is None:
        return redirect('signup')

    heading_text = [
        "Post your thoughts",
        "What’s on your mind?",
        "How are we feeling?",
        "Got something to share?",
        "Drop today’s entry",
        "Even the smallest wins are worth sharing",
        "Anything you want to talk about?",
        "What's up?"
    ]
    entry_heading = random.choice(heading_text)
    process_inbox(request.current_author)

    form = EntryForm()
    editing_entry = None

    entries = Entry.objects.exclude(visibility="DELETED").order_by('-is_posted')
    context = {
        "form": form,
        "editing_entry": editing_entry,
        "entries": entries,
        "entry_heading": entry_heading,
        "comment_form": CommentForm(),
    }
    host = settings.SITE_URL.rstrip("/")

    # FEATURE: CREATE A NEW ENTRY
    if request.method == "POST" and "entry_post" in request.POST:
        entry_id = f"{host}/api/entry/{uuid.uuid4()}"

        user_selected_visibility = request.POST.get("visibility", "PUBLIC")
        
        # Ensure visibility is uppercase for consistency
        if user_selected_visibility:
            user_selected_visibility = user_selected_visibility.upper()
        
        print(f"[DEBUG entry_post] Creating entry with visibility: {user_selected_visibility}")
        
        if not validate_visibility(user_selected_visibility):
            return redirect("stream")

        # get the markdown information
        contentType = request.POST.get("markdown", "text/plain")
        if contentType == 'text/markdown':
            markdown_content = request.POST.get("content", "")
            html_content = sanitize_markdown_to_html(markdown_content)
        else:
            html_content = request.POST.get("content", "")

        title = escape(request.POST.get("title", ""))

        with transaction.atomic():
            entry = Entry.objects.create(
                id=entry_id,
                author=request.current_author,
                title=title,
                content=html_content,
                contentType=contentType,
                visibility=user_selected_visibility,
            )

            images = request.FILES.getlist("images")
            for idx, image in enumerate(images):
                EntryImage.objects.create(
                    id=f"{host}/api/images/{uuid.uuid4()}",
                    entry=entry,
                    image=image,
                    order=idx,
                    name=image.name,
                )

        activity = create_new_entry_activity(request.current_author, entry)
        distribute_activity(activity, actor=request.current_author)
        return redirect("stream")

    # FEATURE: EDIT AN EXISTING ENTRY
    if request.method == "POST" and "entry_update" in request.POST:
        primary_key = request.POST.get("entry_update")
        editing_entry = get_object_or_404(Entry, id=primary_key)
        contentType = request.POST.get("markdown", editing_entry.contentType)

        if editing_entry.author.id != request.current_author.id:
            return HttpResponseForbidden("You don't have permission to edit this entry")

        raw_markdown = request.POST.get("content", "")
        # Get visibility from POST - don't default to current visibility, require explicit value
        user_selected_visibility = request.POST.get("visibility", "").strip()
        
        # If visibility not provided in POST, use current visibility as fallback
        if not user_selected_visibility:
            user_selected_visibility = editing_entry.visibility
        
        # Ensure visibility is uppercase for consistency
        user_selected_visibility = user_selected_visibility.upper()

        print(f"[DEBUG entry_update] POST visibility value: '{request.POST.get('visibility', 'NOT PROVIDED')}'")
        print(f"[DEBUG entry_update] Current entry visibility: {editing_entry.visibility}")
        print(f"[DEBUG entry_update] Selected visibility: {user_selected_visibility}")
        print(f"[DEBUG entry_update] Visibility change: {editing_entry.visibility} -> {user_selected_visibility}")

        if not validate_visibility(user_selected_visibility):
            print(f"[DEBUG entry_update] ERROR: Invalid visibility: {user_selected_visibility}")
            return redirect("stream")

        if contentType == 'text/plain':
            html_content = raw_markdown
        else:
            html_content = sanitize_markdown_to_html(raw_markdown)
        title = bleach.clean(request.POST.get("title", editing_entry.title) or editing_entry.title)

        new_images = request.FILES.getlist("images")
        remove_images = request.POST.getlist("remove_images")

        with transaction.atomic():
            old_visibility = editing_entry.visibility
            editing_entry.title = title
            editing_entry.content = html_content
            editing_entry.visibility = user_selected_visibility
            editing_entry.contentType = "text/plain"
            editing_entry.save()
            
            print(f"[DEBUG entry_update] Successfully updated entry {editing_entry.id}")
            print(f"[DEBUG entry_update] Visibility changed from {old_visibility} to {editing_entry.visibility}")

            if remove_images:
                EntryImage.objects.filter(entry=editing_entry, id__in=remove_images).delete()

            if new_images:
                current_max = editing_entry.images.count()
                for idx, f in enumerate(new_images):
                    EntryImage.objects.create(
                        id=f"{host}/api/images/{uuid.uuid4()}",
                        entry=editing_entry,
                        image=f,
                        name=f.name,
                        order=current_max + idx,
                    )

            activity = create_update_entry_activity(request.current_author, editing_entry)
            distribute_activity(activity, actor=request.current_author)

        context.update({
            "form": EntryForm(),
            "editing_entry": None,
            "entries": Entry.objects.exclude(visibility="DELETED").order_by('-is_posted'),
        })
        return render(request, "new_post.html", context)

    # FEATURE: ENTER EDIT MODE 
    if request.method == "POST" and "entry_edit" in request.POST:
        primary_key = request.POST.get("entry_edit")
        editing_entry = get_object_or_404(Entry, id=primary_key)

        if editing_entry.author.id != request.current_author.id:
            return HttpResponseForbidden("You don't have permission to edit this entry")

        content = editing_entry.content
        if editing_entry.contentType == 'text/markdown':
            content = html_to_markdown(content)
        form = EntryForm(instance=editing_entry)
        context.update({
            "editing_entry": editing_entry,
            "content": content,
            "form": form,
            "entries": Entry.objects.exclude(visibility="DELETED").order_by('-is_posted'),
        })
        return render(request, "new_post.html", context)

   
    # DEFAULT: Show an Empty Form 
    return render(request, "new_post.html", context)

@login_required
def entry_detail_view(request, entry_uuid):
    ''' 
    Primary view to see specific entry details with editing and deletion features if
    the author owns that entry.
    '''
    try:
        entry = Entry.objects.get(id=entry_uuid)
    except Entry.DoesNotExist:
        entry = get_object_or_404(Entry, id__endswith=str(entry_uuid))
    
    if entry.visibility == 'DELETED':
        return redirect('stream')
            
    viewer = Author.from_user(request.user)
    #people following the user
    followers_qs = Author.objects.filter(following=viewer)
    following_qs = Author.objects.filter(followers_set=viewer)

    followers = followers_qs.values_list("id", flat=True)
    following = following_qs.values_list("id", flat=True)

    friends = followers_qs.intersection(following_qs).values_list("id", flat=True)
    process_inbox(viewer)

    if entry.visibility == "FRIENDS":
        if viewer != entry.author:
            is_friend = False
            if viewer:
                is_friend = False
                if viewer.id in friends:
                    is_friend = True
                '''
                viewer_follows_author = Follow.objects.filter(
                    actor=viewer,
                    object=entry.author.id,
                    state="ACCEPTED"
                ).exists()
                if viewer_follows_author:
                    author_follows_viewer = Follow.objects.filter(
                        actor=entry.author,
                        object=viewer.id,
                        state="ACCEPTED"
                    ).exists()
                    is_friend = author_follows_viewer
                '''
            if not is_friend:
                return HttpResponseForbidden("This post is visible to friends only.")
    elif entry.visibility == "UNLISTED":
        if viewer != entry.author:
            is_follower = False
            if viewer.id in following:
                is_follower = True
            '''
            is_friend = False
            is_follower = Follow.objects.filter(
                actor=viewer,
                object=entry.author.id,
                state="ACCEPTED"
            ).exists()
            '''
            is_friend = False
            if viewer.id in friends:
                    is_friend = True
            '''
            if viewer and is_follower:
                is_friend = Follow.objects.filter(
                    actor=entry.author,
                    object=viewer.id,
                    state="ACCEPTED"
                ).exists()
            '''
            if not (is_follower or is_friend):
                return HttpResponseForbidden("You don't have permission to view this entry.")
    
    # FEATURE: DELETE AN ENTRY
    if request.method == "POST" and "entry_delete" in request.POST:
        # Validation and sanitization for security checking that it's their own entry 
        if entry.author.id != viewer.id:
            return HttpResponseForbidden("You don't have permission to delete this entry")
        
        entry.visibility = 'DELETED'
        entry.save()
        
        activity = create_delete_entry_activity(viewer, entry)
        distribute_activity(activity, actor=viewer)

        return redirect('stream')
    
    # FEATURE: EDIT BUTTON CLICKED
    if request.method == "POST" and "entry_edit" in request.POST: # Edit_entry flag for security 
        if entry.author.id != viewer.id:
            return HttpResponseForbidden("You don't have permission to edit this entry")
        return redirect('new_edit_entry_view') 

    # FEATURE: DISPLAY ENTRY AND COMMENTS
    # Refresh remote author username if it looks like a UUID
    if entry.author and not is_local(entry.author.id):
        username_looks_like_uuid = len(entry.author.username) == 36 and '-' in entry.author.username and entry.author.username.count('-') == 4
        if username_looks_like_uuid or entry.author.username.startswith("http") or entry.author.username == "goldenuser":
            updated_author = get_or_create_foreign_author(entry.author.id)
            if updated_author and updated_author.username != entry.author.username:
                entry.author.username = updated_author.username
    
    # Process inbox for the entry author to get latest likes/comments from remote nodes
    # This ensures we see the most up-to-date likes/comments even if the author hasn't visited their page
    process_inbox(entry.author)
    
    comments_qs = entry.comment.select_related('author').order_by('-published')
    serialized_comments = CommentSerializer(comments_qs, many=True).data
    entry_comments = {entry.id: serialized_comments}

    context = {
        'entry': entry,
        'comments': comments_qs,
        'comment_form': CommentForm(),
        'entry_comments_json': json.dumps(entry_comments),
        'is_owner': (viewer == entry.author), # For showing edit/delete buttons
    }

    return render(request, 'entry_detail.html', context)

FOLLOW_STATE_CHOICES = ["REQUESTED", "ACCEPTED", "REJECTED"]

@login_required
def profile_view(request):
    """This function deals the primary logic regarding profile.html."""

    def get_remote_authors(node):
        """Fetch all authors from a remote node."""
        # Construct API URL properly s.t the node.id should already be the base URL
        node_base = node.id.rstrip('/')
        api_url = f"{node_base}/api/authors/"
        auth = (node.auth_user, node.auth_pass) if node.auth_user else None
        
        "ChatGPT: Credits: 11-22-2025"
        """
        This code attempts to fetch all authors from a remote node.
        It handles both paginated format (with "items") and direct list format.
        It also handles authentication failures and endpoint not found errors.
        """
        try:
            response = requests.get(
                api_url,
                timeout=10,
                auth=auth,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 200:
                data = response.json()
                # Handle both paginated format (with "items") and direct list format
                if isinstance(data, dict):
                    if "items" in data:
                        items = data["items"]
                        if isinstance(items, list):
                            return items
                        else:
                            print(f"[REMOTE AUTHORS] 'items' is not a list from {node.id}/api/authors/")
                            return []

                    if "authors" in data and isinstance(data["authors"], list):
                        return data["authors"]

                    print("[REMOTE AUTHORS] Unexpected dict format:", data)
                    return []
                elif isinstance(data, list):
                    return data
                else:
                    print(f"[REMOTE AUTHORS] Unexpected response format from {node.id}/api/authors/: {type(data)}")
                    return []
            elif response.status_code == 401:
                print(f"[REMOTE AUTHORS] Authentication failed for {node.id}. Check auth_user and auth_pass.")
                print(f"[REMOTE AUTHORS] Current auth_user: {node.auth_user or 'None'}")
                return []
            elif response.status_code == 404:
                print(f"[REMOTE AUTHORS] Endpoint not found: {api_url}")
                return []
            else:
                print(f"[REMOTE AUTHORS] Error fetching from {node.id}: HTTP {response.status_code}")
                print(f"[REMOTE AUTHORS] Response: {response.text[:200]}")
                return []
        except requests.exceptions.Timeout:
            print(f"[REMOTE AUTHORS] Timeout connecting to {node.id}")
            return []
        except requests.exceptions.ConnectionError as e:
            print(f"[REMOTE AUTHORS] Connection error to {node.id}: {e}")
            return []
        except requests.exceptions.RequestException as e:
            print(f"[REMOTE AUTHORS] Request error for {node.id}: {e}")
            return []
        except Exception as e:
            print(f"[REMOTE AUTHORS] Unexpected error fetching from {node.id}: {e}")
            return []

    def get_friends_context(author: Author):
        """
        Get friends (mutual follows) for both local and remote authors.
        Uses Follow objects to work with remote authors.
        """
        # Use get_friends which works with Follow objects for both local and remote
        friends_qs = get_friends(author)
        friend_ids = set(f.id for f in friends_qs) 
        return friends_qs, friend_ids

    def sync_github_activity(author):
        """Fetch public GitHub events for the author and create public Entries automatically."""
        if not author.github:
            return

        username = author.github.rstrip('/').split('/')[-1]
        api_url = f"https://api.github.com/users/{username}/events/public"

        try:
            response = requests.get(api_url, timeout=5)
            if response.status_code != 200:
                print(f"Failed to fetch GitHub events: {response.status_code}")
                return
            events = response.json()
        except Exception as e:
            print(f"Error fetching GitHub events: {e}")
            return

        for event in events:
            event_id = event.get("id")
            event_type = event.get("type")
            repo_name = event.get("repo", {}).get("name", "unknown repo")
            repo_url = f"https://github.com/{repo_name}"
            created_at = event.get("created_at")

            entry_id = f"{author.host}/authors/{author.id}/entries/github-{event_id}"

            if Entry.objects.filter(id=entry_id).exists():
                continue

            content_text = ""
            if event_type == "PushEvent":
                commits = event.get("payload", {}).get("commits", [])
                messages = []
                for c in commits:
                    sha = c.get("sha")[:7]
                    msg = c.get("message", "")
                    url = c.get("url", "").replace("api.", "").replace("repos/", "").replace("commits", "commit")
                content_text = f"**Pushed to [{repo_name}]({repo_url})**:\n\n" + "\n".join(messages)

            elif event_type == "IssuesEvent":
                issue = event.get("payload", {}).get("issue", {})
                issue_url = issue.get("html_url", "")
                content_text = f"**Issue in [{repo_name}]({repo_url})**: [{issue.get('title', '')}]({issue_url})\n\n{issue.get('body', '')}"

            elif event_type == "PullRequestEvent":
                pr = event.get("payload", {}).get("pull_request", {})
                pr_url = pr.get("html_url", "")
                content_text = f"**Pull Request in [{repo_name}]({repo_url})**: [{pr.get('title', '')}]({pr_url})\n\n{pr.get('body', '')}"

            else:
                content_text = f"**{event_type}** in [{repo_name}]({repo_url})"

            html_content = markdown.markdown(content_text)

            Entry.objects.create(
                id=entry_id,
                author=author,
                title=f"{event_type} on {repo_name} (GitHub)",
                content=html_content,
                contentType="text/html",
                visibility="PUBLIC",
                source=author.github,
                origin=author.github,
                published=created_at,
                is_posted=dj_timezone.now()
            )

    def get_search_authors(author: Author, query: str):
        """
        Search for authors, both local and remote.
        Simplified version matching working local implementation pattern.
        """
        results = []
        query = query.strip() if query else ""
        
        # Local authors logic by search ALL authors in database (includes local + remote stubs)
        local_qs = Author.objects.exclude(id=author.id)
        print("logged_in_author_id =", author.id)
        if query:
            local_qs = local_qs.filter(Q(username__icontains=query) | Q(name__icontains=query))
        
        for a in local_qs:
            is_local_author = is_local(a.id)
            print("comparing against IDs:", a.id) 
            results.append({
                "id": a.id,
                "url_id": fqid_to_uuid(a.id) if is_local_author else str(a.id).rstrip('/'),
                "username": a.username,
                "displayName": getattr(a, 'displayName', None) or getattr(a, 'name', None) or a.username,
                "profileImage": getattr(a, 'profileImage', '') or '',
                "github": getattr(a, 'github', '') or '',
                "web": getattr(a, 'web', '') or '',
                "is_local": is_local_author,
                "host": a.host or str(a.id).split('/api/authors/')[0] if '/api/authors/' in str(a.id) else '',
            })

        # Remote authors logic by fetching from active nodes
        nodes = Node.objects.filter(is_active=True)
        print(f"[SEARCH DEBUG] Found {nodes.count()} active nodes to fetch from")
        if nodes.count() == 0:
            print(f"[SEARCH DEBUG] WARNING: No active nodes found in database! Remote authors won't be available.")
            print(f"[SEARCH DEBUG] To add a node, use Django admin or run: python manage.py shell < add_remote_node.py")
        
        "ChatGPT: Credits: 11-22-2025"
        """
        This code fetches remote authors from active nodes.
        It handles both paginated format (with "items") and direct list format.
        It also handles authentication failures and endpoint not found errors.
        """
        for node in nodes:
            print(f"[SEARCH DEBUG] Fetching authors from node: {node.id} (auth_user={node.auth_user or 'None'})")
            remote_authors = get_remote_authors(node)
            print(f"[SEARCH DEBUG] Got {len(remote_authors)} authors from {node.id}")
            for ra in remote_authors:
                if not ra or not isinstance(ra, dict):
                    continue
                
                ra_id = ra.get("id") or ra.get("@id") or str(ra.get("url", ""))
                if not ra_id:
                    continue
                
                ra_id_clean = str(ra_id).rstrip('/')
                
                # Skip if already in results (from database)
                if any(r.get("id") == ra_id_clean for r in results):
                    continue
                
                if is_local(ra_id):
                    continue

                #if not is_local_to_node(ra_id, node)          FIX THIS LATER
                    #continue

                # Get username and displayName
                ra_username = ra.get("username") or ra.get("displayName")
                if not ra_username and "/api/authors/" in str(ra_id):
                    ra_username = str(ra_id).split("/api/authors/")[-1].rstrip("/")
                if not ra_username:
                    ra_username = str(ra_id).split("/")[-1] or "Unknown"
                
                ra_displayName = ra.get("displayName") or ra.get("display_name") or ra_username
                
                # Get host
                ra_host = ra.get("host")
                if not ra_host and "/api/authors/" in str(ra_id):
                    parsed = urlparse(ra_id)
                    ra_host = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
                if not ra_host:
                    ra_host = node.id.rstrip('/')
                
                # Search matching - if query exists, filter by username and displayName
                # If query is empty, show all remote authors
                if query:
                    username_match = query.lower() in ra_username.lower() if ra_username else False
                    displayName_match = query.lower() in ra_displayName.lower() if ra_displayName else False
                    if not username_match and not displayName_match:
                        continue
                
                results.append({
                    "id": ra_id_clean,
                    "url_id": fqid_to_uuid(ra_id) if is_local(ra_id) else str(ra_id).rstrip('/'),
                    "username": ra_username,
                    "displayName": ra_displayName,
                    "profileImage": ra.get("profileImage") or ra.get("profile_image") or (ra.get("icon", {}).get("url", '') if isinstance(ra.get("icon"), dict) else ra.get("icon", '')) or '',
                    "github": ra.get("github") or '',
                    "web": ra.get("web") or '',
                    "is_local": False,
                    "host": ra_host,
                })

        return results
    
    author = Author.from_user(request.user)
    
    # Fetch followers and following for the current author
    followers_qs = Author.objects.filter(following=author)
    following_qs = Author.objects.filter(followers_set=author)
    friends = followers_qs.intersection(following_qs)
    print(f"[DEBUG profile_view] Author {author.username} has {followers_qs.count()} followers, {following_qs.count()} following, {friends.count()} friends")
    

    # Add 'url_id' or 'uuid' to each author where Local -> uuid and Remote -> FQID
    for a in followers_qs:
        a.url_id = fqid_to_uuid(a.id) if is_local(a.id) else a.id  

    for a in following_qs:
        a.url_id = fqid_to_uuid(a.id) if is_local(a.id) else a.id  #

    # Process inbox FIRST to create Follow objects from remote follow requests
    # This must happen before querying for follow requests
    print(f"[DEBUG profile_view] Processing inbox for author={author.username} (id={author.id})")
    process_inbox(author)
    print(f"[DEBUG profile_view] Finished processing inbox")

    form = ProfileForm(instance=author)

    # Fetch INCOMING follow requests (requests TO the author)
    # Follow objects from process_inbox use normalized object IDs, so we need to normalize for matching
    #   - When a REMOTE author sends a follow request to a LOCAL author:
    #     1. Remote node sends Follow activity to local author's inbox
    #     2. process_inbox() creates Follow object with actor=remote_author, object=local_author.id (normalized)
    #     3. Query matches Follow.objects.filter(object=local_author.id_normalized)
    #   - When a LOCAL author sends a follow request to a REMOTE author:
    #     1. Local creates Follow object with actor=local_author, object=remote_author.id (normalized)
    #     2. Query matches Follow.objects.filter(object=remote_author.id_normalized)
    # The key is that process_inbox() ensures object field always matches the inbox author's ID
    author_id_str = str(author.id).rstrip('/')
    author_id_normalized = normalize_fqid(author_id_str)
    
    # Query for incoming requests, you need to match the object field (which is the target being followed)
    # Try multiple variations to handle normalization differences (for both local and remote)
    # We check both normalized and raw versions to handle existing data
    query_conditions = (
        Q(object=author_id_normalized) | 
        Q(object=author_id_str) | 
        Q(object__iexact=author_id_str) |
        Q(object__iexact=author_id_normalized) |
        # Also check with trailing slash variations
        Q(object=f"{author_id_str}/") |
        Q(object=f"{author_id_normalized}/")
    )
    
    # Also try matching by UUID/FQID suffix if applicable
    if '/' in author_id_str:
        author_uuid_or_id = author_id_str.split('/')[-1]
        query_conditions |= Q(object__icontains=author_uuid_or_id)
    
    # Query for incoming requests - use a more comprehensive approach
    # IMPORTANT: Only show REQUESTED state, exclude REJECTED and ACCEPTED
    # First try the exact matches
    incoming_follow_requests = Follow.objects.filter(
        state="REQUESTED"  # Only show pending requests, not rejected or accepted
    ).filter(query_conditions).distinct()
    
    # If no results, try a more lenient approach, otherwise check if any part of the object field matches
    if incoming_follow_requests.count() == 0:
        # Try matching by author ID in any form (case-insensitive, with/without trailing slash)
        author_id_variations = [
            author_id_str,
            author_id_normalized,
            author_id_str.rstrip('/'),
            author_id_normalized.rstrip('/'),
            author_id_str.lower(),
            author_id_normalized.lower(),
        ]
        # Add UUID if it's a local author
        if '/' in author_id_str:
            uuid_part = author_id_str.split('/')[-1]
            if uuid_part and '-' in uuid_part:
                author_id_variations.append(uuid_part)
                author_id_variations.append(uuid_part.lower())
        
        # CHATGPT Credits: 11-22-2025: Build a more lenient query
        lenient_conditions = Q()
        for variation in author_id_variations:
            lenient_conditions |= Q(object__iexact=variation) | Q(object__icontains=variation)
        
        incoming_follow_requests = Follow.objects.filter(
            state="REQUESTED"  # Only show pending requests, not rejected or accepted
        ).filter(lenient_conditions).distinct()
    
    outgoing_count = Follow.objects.filter(actor=author, state="REQUESTED").count()
            
    # Fetch OUTGOING follow requests (requests FROM the author)
    outgoing_follow_requests = Follow.objects.filter(actor=author, state="REQUESTED")

    if request.method == "GET":
        sync_github_activity(author)

    if request.method == "POST":
        if "follow_id" in request.POST and "action" in request.POST:
            follow_id = request.POST.get("follow_id")
            action = request.POST.get("action")

            if not follow_id:
                return redirect("profile")
            
            # Normalize author ID to match Follow objects created by process_inbox
            author_id_normalized = normalize_fqid(str(author.id))
            author_id_str = str(author.id).rstrip('/')
            
            # Query for the follow request - handle both normalized and raw IDs (for local and remote)
            follow_request = Follow.objects.filter(
                id=follow_id
            ).filter(
                Q(object=author_id_normalized) | 
                Q(object=author_id_str) | 
                Q(object__iexact=author_id_str) |
                Q(object__iexact=author_id_normalized)
            ).first()
            
            if not follow_request:
                return redirect("profile")

            target_author = follow_request.actor
            
            if action == "approve":
                follow_request.state = "ACCEPTED"
                follow_request.save()
                target_author.following.add(author)
                
                # Mark inbox item as processed if it exists
                inbox_item = Inbox.objects.filter(author=author, data__id=follow_id, processed=False).first()
                if inbox_item:
                    inbox_item.processed = True
                    inbox_item.save()

                # Send Accept activity
                #activity = create_accept_follow_activity(author, follow_id)
                #distribute_activity(activity, actor=author)

            elif action == "reject":
                follow_request.state = "REJECTED"
                follow_request.save()

                # Mark inbox item as processed if it exists
                inbox_item = Inbox.objects.filter(author=author, data__id=follow_id, processed=False).first()
                if inbox_item:
                    inbox_item.processed = True
                    inbox_item.save()

                # Send Reject activity
                #activity = create_reject_follow_activity(author, follow_id)
                #distribute_activity(activity, actor=author)

            return redirect("profile")

        # Handle remove-follower (from followers tab) - supports both hyphen and underscore
        if "remove-follower" in request.POST or "remove_follower" in request.POST:
            target_id = request.POST.get("remove-follower") or request.POST.get("remove_follower")
            print(f"[DEBUG profile_view] REMOVE FOLLOWER: Removing follower: author={author.username}, target_id={target_id}")
            
            try:
                # Try to find target with normalized ID first
                target = Author.objects.filter(id=normalize_fqid(target_id)).first()
                if not target:
                    target = Author.objects.filter(id=target_id).first()
                if not target:
                    target = get_or_create_foreign_author(target_id)
                
                if target:
                    print(f"[DEBUG profile_view] REMOVE FOLLOWER: Found target: {target.username} (id={target.id})")
                    
                    # Remove from ManyToMany relationship (for local authors)
                    if target in author.followers_set.all():
                        author.followers_set.remove(target)
                        print(f"[DEBUG profile_view] REMOVE FOLLOWER: Removed {target.username} from {author.username}'s followers_set")
                    
                    # Delete Follow objects - normalize IDs for consistent matching
                    author_id_normalized = normalize_fqid(str(author.id))
                    author_id_str = str(author.id).rstrip('/')
                    target_id_normalized = normalize_fqid(str(target.id))
                    target_id_str = str(target.id).rstrip('/')
                    
                    deleted = Follow.objects.filter(
                        actor=target
                    ).filter(
                        Q(object=author_id_normalized) | 
                        Q(object=author_id_str) | 
                        Q(object__iexact=author_id_str) |
                        Q(object__iexact=author_id_normalized) |
                        Q(object=target_id_normalized) |
                        Q(object=target_id_str)
                    ).delete()
                    
                    print(f"[DEBUG profile_view] REMOVE FOLLOWER: Deleted {deleted[0]} Follow objects")
                    
                else:
                    print(f"[DEBUG profile_view] REMOVE FOLLOWER: ERROR - Target not found: {target_id}")
            except Exception as e:
                print(f"[DEBUG profile_view] REMOVE FOLLOWER: Exception: {type(e).__name__}: {e}")

            return redirect("profile")
        
        if "unfollow" in request.POST:
            target_id = request.POST.get("unfollow")
            try:
                target = Author.objects.get(id=target_id)
                author.following.remove(target)
                # Normalize target ID for consistent matching
                target_id_normalized = normalize_fqid(str(target.id))
                target_id_str = str(target.id).rstrip('/')
                Follow.objects.filter(actor=author).filter(
                    Q(object=target_id_normalized) | 
                    Q(object=target_id_str) | 
                    Q(object__iexact=target_id_str) |
                    Q(object__iexact=target_id_normalized)
                ).delete()

                #activity = create_unfollow_activity(author, target_id)
                #distribute_activity(activity, actor=author)
                messages.success(request, f"Unfollowed {target.username}")
            except Author.DoesNotExist:
                messages.error(request, "Author not found")

            return redirect("profile")

        if request.POST.get("action") == "follow":
            target_id = request.POST.get("author_id")
            target_host = request.POST.get("host")

            print(f"[DEBUG profile_view] FOLLOW ACTION: actor={author.username} (id={author.id})")
            print(f"[DEBUG profile_view] FOLLOW ACTION: target_id={target_id}, target_host={target_host}")

            if not target_id:
                print(f"[DEBUG profile_view] FOLLOW ACTION: ERROR - No target_id provided")
                return redirect("profile")
            
            # Get or create the target author (local or remote)
            target = Author.objects.filter(id=target_id).first()
            print(f"[DEBUG profile_view] FOLLOW ACTION: Lookup by FQID: target={target.username if target else 'None'} (id={target.id if target else 'None'})")
            
            # Try to find by username if it's a local author (UUID)
            if not target:
                target_username = request.POST.get("displayName") or request.POST.get("username")
                print(f"[DEBUG profile_view] FOLLOW ACTION: Target not found by FQID, trying username lookup: target_username={target_username}")
                if target_username and ('-' not in str(target_id).split('/')[-1] or is_local(target_id)):
                    target = Author.objects.filter(username=target_username).first()
                    print(f"[DEBUG profile_view] FOLLOW ACTION: Lookup by username: target={target.username if target else 'None'} (id={target.id if target else 'None'})")
            
            if not target:
                # If author doesn't exist locally, create a foreign author stub
                target_username = request.POST.get("username") or request.POST.get("displayName")
                print(f"[DEBUG profile_view] FOLLOW ACTION: Target not found, calling get_or_create_foreign_author: target_id={target_id}, host={target_host}, username={target_username}")
                try:
                    target = get_or_create_foreign_author(target_id, host=target_host, username=target_username)
                    print(f"[DEBUG profile_view] FOLLOW ACTION: get_or_create_foreign_author returned: target={target.username if target else 'None'} (id={target.id if target else 'None'})")
                except TypeError as e:
                    # Defensive: if services signature mismatched or unexpected error
                    print(f"[DEBUG profile_view] FOLLOW ACTION: TypeError in get_or_create_foreign_author: {e}")
                    return redirect("profile")
                except Exception as e:
                    print(f"[DEBUG profile_view] FOLLOW ACTION: Exception in get_or_create_foreign_author: {type(e).__name__}: {e}")
                    return redirect("profile")

                if not target:
                    print(f"[DEBUG profile_view] FOLLOW ACTION: ERROR - get_or_create_foreign_author returned None")
                    return redirect("profile")

            # Normalize target.id to ensure consistent matching with Follow objects from process_inbox
            target_id_normalized = normalize_fqid(str(target.id))
            print(f"[DEBUG profile_view] FOLLOW ACTION: Creating Follow object: actor={author.username} (id={author.id}), object={target_id_normalized}")
            if is_local(target_id_normalized):
                follow, created = Follow.objects.get_or_create(
                    actor=author,
                    object=target_id_normalized,  # Use normalized ID for consistency
                    defaults={
                        "id": f"{author.id.rstrip('/')}/follow/{uuid.uuid4()}",
                        "summary": f"{author.username} wants to follow {target.username}",
                        "published": dj_timezone.now(),
                        "state": "REQUESTED",
                    },
                )
            else:
                author.following.add(target)

            #print(f"[DEBUG profile_view] FOLLOW ACTION: Follow object {'created' if created else 'already exists'}: follow.id={follow.id}, follow.state={follow.state}")

            print(f"[DEBUG profile_view] FOLLOW ACTION: Creating follow activity")
            activity = create_follow_activity(author, target)
            print(f"[DEBUG profile_view] FOLLOW ACTION: Activity created: type={activity.get('type')}, actor={activity.get('actor')}, object={activity.get('object')}")
            
            print(f"[DEBUG profile_view] FOLLOW ACTION: Distributing activity")
            distribute_activity(activity, actor=author)
            print(f"[DEBUG profile_view] FOLLOW ACTION: Activity distributed successfully")
            
            return redirect("profile")

        if "remove_friend" in request.POST:
            target_id = request.POST.get("remove_friend")
            try:
                target = Author.objects.get(id=target_id)
                author.following.remove(target)
                target.following.remove(author)
                Follow.objects.filter(actor=author, object=target.id).delete()
                Follow.objects.filter(actor=target, object=author.id).delete()

                #activity = create_unfriend_activity(author, target_id)
                #distribute_activity(activity, actor=author)
            except Author.DoesNotExist:
                messages.error(request, "Author not found")

            return redirect("profile")

        if "edit_profile" in request.POST:
            form = ProfileForm(request.POST, request.FILES, instance=author)
            if form.is_valid():
                form.save()
                activity = create_profile_update_activity(author)
                distribute_activity(activity, actor=author)

            return redirect("profile")

    # IMPORTANT: Process inbox BEFORE querying for follow requests
    # This ensures any incoming follow requests from remote nodes are processed first
    process_inbox(author)
    
    # Get viewer (who is viewing this profile) - for visibility filtering
    viewer = author # When viewing own profile, viewer is the author
    if request.user.is_authenticated:
        viewer_author = Author.from_user(request.user)
        if viewer_author and viewer_author != author:
            viewer = viewer_author
    
    entries_qs = Entry.objects.filter(author=author).exclude(visibility="DELETED")
    
    if viewer == author:
        entries = entries_qs.order_by("-published")
    else:
        visible_entries = []
        
        followed_by_viewer = False
        if viewer:
            followed_by_viewer = Follow.objects.filter(
                actor=viewer,
                object=author.id,
                state="ACCEPTED"
            ).exists()
        
        is_friend_with_viewer = False
        if viewer and followed_by_viewer:
            # Check if author also follows viewer (mutual follow = friends)
            is_friend_with_viewer = Follow.objects.filter(
                actor=author,
                object=viewer.id,
                state="ACCEPTED"
            ).exists()
        
        for entry in entries_qs:
            if entry.visibility == "PUBLIC":
                visible_entries.append(entry)
            elif entry.visibility == "UNLISTED" and followed_by_viewer:
                visible_entries.append(entry)
            elif entry.visibility == "FRIENDS" and is_friend_with_viewer:
                visible_entries.append(entry)
        
        entries = sorted(visible_entries, key=lambda x: x.published, reverse=True)
        
    followers = get_followers(author)
    
    # Get following (people this author follows) - works for both local and remote
    # The object field is a URLField (FQID string), so we need to handle both exact matches and normalized
    following_follows = Follow.objects.filter(actor=author, state="ACCEPTED")
    following_ids = []
    following_ids_normalized = []
    for f in following_follows:
        following_ids.append(f.object)
        following_ids_normalized.append(normalize_fqid(str(f.object))) 
    
    # Try to find authors by both raw and normalized IDs
    #following = Author.objects.filter(
        #Q(id__in=following_ids) | Q(id__in=following_ids_normalized)
    #).distinct()
    following = Author.objects.filter(followers_set=author)
    
    friends_qs = get_friends(author)
    
    followers_with_urls = [{'author': f, 'url_id': fqid_to_uuid(f.id) if is_local(f.id) else f.id.rstrip('/')} for f in followers]
    following_with_urls = [{'author': f, 'url_id': fqid_to_uuid(f.id) if is_local(f.id) else f.id.rstrip('/')} for f in following]
    friends_with_urls = [{'author': f, 'url_id': fqid_to_uuid(f.id) if is_local(f.id) else f.id.rstrip('/')} for f in friends_qs]

    follow_requests_with_urls = []
    for req in outgoing_follow_requests:
        target_id = req.object
        target_id_normalized = normalize_fqid(str(target_id))
        target_id_str = str(target_id).rstrip('/')
        
        target = Author.objects.filter(
            Q(id=target_id_normalized) | Q(id=target_id_str) | Q(id__iexact=target_id_str)
        ).first()
        
        # If target not found, fetch from remote node
        if not target:
            print(f"[DEBUG profile_view] OUTGOING REQUEST: Target not found locally, fetching from remote: {target_id_str}")
            target = get_or_create_foreign_author(target_id_str)
            if target:
                print(f"[DEBUG profile_view] OUTGOING REQUEST: Fetched target: {target.username} (id={target.id})")
        
        # If target not found, fetch from remote node
        if not target:
            target = get_or_create_foreign_author(target_id_str)
        
        if target:
            follow_requests_with_urls.append({
                'request': req, 
                'target': target,
                'target_url_id': fqid_to_uuid(target.id) if is_local(target.id) else target.id.rstrip('/')
            })
            print(f"[DEBUG profile_view] OUTGOING REQUEST: Added to list with target.username={target.username}")
        else:
            # If still not found, add with FQID as fallback
            # If still not found, add with target_id for display
            print(f"[DEBUG profile_view] OUTGOING REQUEST: Could not fetch target, adding with FQID only")
            follow_requests_with_urls.append({
                'request': req,
                'target': None,
                'target_url_id': target_id_str,
                'target_id': target_id_str
            })
    
    # Also process INCOMING follow requests for approval/rejection
    print(f"[DEBUG profile_view] Processing {len(incoming_follow_requests)} incoming follow requests")
    incoming_follow_requests_with_urls = []
    for req in incoming_follow_requests:
        print(f"[DEBUG profile_view] INCOMING REQUEST: req.id={req.id}, req.actor={req.actor}, req.object={req.object}, req.state={req.state}")
        # Make sure actor exists (it should be a ForeignKey, but check just in case)
        if req.actor:
            # Ensure actor has username (fetch if remote and missing)
            actor_to_use = req.actor
            if not req.actor.username or req.actor.username == "goldenuser" or req.actor.username.startswith("http"):
                # Try to fetch remote author data if username is missing or looks like an FQID
                if not is_local(req.actor.id):
                    updated_actor = get_or_create_foreign_author(req.actor.id)
                    if updated_actor and updated_actor.username and updated_actor.username != "goldenuser":
                        actor_to_use = updated_actor
            
            incoming_follow_requests_with_urls.append({
                'request': req, 
                'actor': actor_to_use,  # Pass the actor with proper username
                'actor_url_id': fqid_to_uuid(actor_to_use.id) if is_local(actor_to_use.id) else actor_to_use.id.rstrip('/')
            })
            print(f"[DEBUG profile_view] INCOMING REQUEST: Added to list with actor.username={actor_to_use.username}")
        else:
            print(f"[DEBUG profile_view] WARNING: Follow request {req.id} has no actor!")
    
    print(f"[DEBUG profile_view] Total incoming follow requests with URLs: {len(incoming_follow_requests_with_urls)}")

    # Sanitize the description for safe HTML display
    author.description = sanitize_markdown_to_html(author.description)

    # Prepare the context to render the profile page
    query = request.GET.get("q", "").strip()
    authors = get_search_authors(author, query)
    
    # Populate follow state and friend status for each author (like your working code)
    friends_qs, friend_ids = get_friends_context(author)
    # Convert friends queryset to list for template checks
    friends_list = list(friends_qs)

    followers_qs = Author.objects.filter(following=author)
    following_qs = Author.objects.filter(followers_set=author)
    following_ids = set(following_qs.values_list("id", flat=True))
    friends = followers_qs.intersection(following_qs).values_list("id", flat=True)
    
    for a in authors:

        # Normalize author ID for consistent Follow object matching (for both local and remote)
        a_id_normalized = normalize_fqid(str(a["id"]))
        a_id_str = str(a["id"]).rstrip('/')

        a_id = a.get("id")

        # Normalize string vs FQID vs plain UUID
        a_id_normalized = normalize_fqid(a_id)
        a_id_str = str(a_id)

        # Is the current user following this author?
        a["is_following"] = (
            str(a_id_normalized) in following_ids or
            str(a_id_str) in following_ids
        )

        # Are they friends?
        a["is_friend"] = (
            str(a_id_normalized) in friend_ids or
            str(a_id_str) in friend_ids
        )

        """
        authors = []
        for a in queryset_of_authors:
            a.is_following = a.id in following_ids
            authors.append(a)
        
        if a.get("is_local"):
            # Local author, checking if follow relationship is stored using normalized ID
            follow = Follow.objects.filter(actor=author).filter(
                Q(object=a_id_normalized) | Q(object=a_id_str) | Q(object__iexact=a_id_str)
            ).first()
            a["follow_state"] = follow.state if follow else "NONE"
            # Use Follow objects instead of ManyToMany for remote compatibility
            a["is_following"] = Follow.objects.filter(
                actor=author,
                object=a["id"],
                state="ACCEPTED"
            ).exists()
            a["is_friend"] = str(a["id"]) in friend_ids
        else:
            # Remote author, checking if we have a follow relationship stored using normalized ID
            follow = Follow.objects.filter(actor=author).filter(
                Q(object=a_id_normalized) | Q(object=a_id_str) | Q(object__iexact=a_id_str)
            ).first()
            a["follow_state"] = follow.state if follow else "NONE"
            a["is_following"] = follow.state == "ACCEPTED" if follow else False
            
            is_following_them = follow and follow.state == "ACCEPTED"
            if is_following_them:
                reciprocal_follow = Follow.objects.filter(
                    actor__id=a_id_normalized,
                    object=normalize_fqid(str(author.id)),
                    state="ACCEPTED"
                ).first()
                if not reciprocal_follow:
                    reciprocal_follow = Follow.objects.filter(
                        Q(actor__id=a_id_normalized) | Q(actor__id=a_id_str),
                        Q(object=normalize_fqid(str(author.id))) | Q(object=str(author.id).rstrip('/')),
                        state="ACCEPTED"
                    ).first()
                a["is_friend"] = reciprocal_follow is not None
            else:
                a["is_friend"] = False
            """
    
    print(f"[SEARCH DEBUG] Profile view - Query: '{query}', Results: {len(authors)}")
    
    
    context = {
        "author": author,
        "entries": entries,
        "followers_with_urls": followers_with_urls,
        "following_with_urls": following_with_urls,
        "friends_with_urls": friends_with_urls,
        "follow_requests_with_urls": follow_requests_with_urls, 
        "incoming_follow_requests_with_urls": incoming_follow_requests_with_urls, 
        "friends": friends_list,
        "form": ProfileForm(instance=author),  
        "authors": authors,
        "query": query,
    }

    return render(request, "profile.html", context)

@login_required
def public_profile_view(request, author_id):
    """
    Display another author's public profile.
    Fetches from remote node if necessary.
    Shows username, github, bio, email, and public entries.
    """

    def get_remote_authors(node):
        """Fetch all authors from a remote node."""
        # Construct API URL properly s.t the node.id should already be the base URL
        node_base = node.id.rstrip('/')
        api_url = f"{node_base}/api/authors/"
        auth = (node.auth_user, node.auth_pass) if node.auth_user else None
        
        "ChatGPT: Credits: 11-22-2025"
        """
        This code attempts to fetch all authors from a remote node.
        It handles both paginated format (with "items") and direct list format.
        It also handles authentication failures and endpoint not found errors.
        """
        try:
            response = requests.get(
                api_url,
                timeout=10,
                auth=auth,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 200:
                data = response.json()
                # Handle both paginated format (with "items") and direct list format
                if isinstance(data, dict):
                    if "items" in data:
                        items = data["items"]
                        if isinstance(items, list):
                            return items
                        else:
                            print(f"[REMOTE AUTHORS] 'items' is not a list from {node.id}/api/authors/")
                            return []

                    if "authors" in data and isinstance(data["authors"], list):
                        return data["authors"]

                    print("[REMOTE AUTHORS] Unexpected dict format:", data)
                    return []
                elif isinstance(data, list):
                    return data
                else:
                    print(f"[REMOTE AUTHORS] Unexpected response format from {node.id}/api/authors/: {type(data)}")
                    return []
            elif response.status_code == 401:
                print(f"[REMOTE AUTHORS] Authentication failed for {node.id}. Check auth_user and auth_pass.")
                print(f"[REMOTE AUTHORS] Current auth_user: {node.auth_user or 'None'}")
                return []
            elif response.status_code == 404:
                print(f"[REMOTE AUTHORS] Endpoint not found: {api_url}")
                return []
            else:
                print(f"[REMOTE AUTHORS] Error fetching from {node.id}: HTTP {response.status_code}")
                print(f"[REMOTE AUTHORS] Response: {response.text[:200]}")
                return []
        except requests.exceptions.Timeout:
            print(f"[REMOTE AUTHORS] Timeout connecting to {node.id}")
            return []
        except requests.exceptions.ConnectionError as e:
            print(f"[REMOTE AUTHORS] Connection error to {node.id}: {e}")
            return []
        except requests.exceptions.RequestException as e:
            print(f"[REMOTE AUTHORS] Request error for {node.id}: {e}")
            return []
        except Exception as e:
            print(f"[REMOTE AUTHORS] Unexpected error fetching from {node.id}: {e}")
            return []

    print("author ------------> ", author_id)

    if author_id.startswith("https"):
        # Remote author
        author_id = normalize_fqid(author_id) # full fqid https://golden-z2-9f0dc8c050fa.herokuapp.com/api/authors/UUID
        
        # Extract host from the FQID
        parsed = urlparse(author_id)
        host = f"{parsed.scheme}://{parsed.netloc}"
        node = Node.objects.filter(id = host).first()
        print("parsed ----------->", parsed)
        print("host ----------->", host)
        print("node ----------->", node)
        
        # Find the node that matches this author
        if not node:
            return render(request, "404.html", {"message": "Node not found"})

        remote_authors = get_remote_authors(node)
        ra = next((a for a in remote_authors if str(a.get("id")).rstrip('/') == author_id), None)
        if not ra:
            return render(request, "404.html", {"message": "Remote author not found"})

        # Wrap the JSON data in a simple object for template
        author = type("RemoteAuthor", (), {})()
        author.username = ra.get("username") or ra.get("displayName") or str(author_id).split("/")[-1]
        author.github = ra.get("github", "")
        author.bio = ra.get("description", "") or ra.get("bio", "")
        author.email = ra.get("email", "")
        profile_image = ra.get("profileImage", "") or ra.get("icon", {}).get("url", "") if isinstance(ra.get("icon"), dict) else ra.get("icon", "")
        author.profileImage = type("Image", (), {"url": profile_image})()

        # Fetch remote entries
        entries = fetch_remote_entries(node)

        context = {
            "is_remote": True,
            "author": author,
            "entries": entries,
        }
    else:
        # Local author
        host = settings.SITE_URL.rstrip("/")
        local_uuid = author_id
        local_fqid = f"{host}/api/authors/{local_uuid}"
        print("local fquid --------> ", local_fqid)
        author = get_object_or_404(Author, id=local_fqid)
        entries = Entry.objects.filter(author=author, visibility="PUBLIC").order_by("-published")
        context = {
            "is_remote": False,
            "author": author,
            "entries": entries
        }

    return render(request, "public_profile.html", context)

# * ============================================================
# * Helper View Functions
# * ============================================================

@login_required
def index(request):
    objects = Author.objects.values()
    print("USERS:")
    for obj in objects:
        print(obj['username']) 
    return render(request, "index.html")

def followers(request):
    actor = Author.from_user(request.user)

    # Handle POST remove follower
    if request.method == "POST":
        follower_id = request.POST.get('author_id')
        follower = get_object_or_404(Author, id=follower_id)

        follower.following.remove(actor)
        follower.save()
        Follow.objects.filter(actor=follower, object=actor.id).delete()

        return redirect(request.META.get('HTTP_REFERER', 'followers'))

    # Use get_followers which works with Follow objects for both local and remote
    followers_qs = get_followers(actor)

    query = request.GET.get('q', '')
    if query:
        followers_qs = followers_qs.filter(username__icontains=query)

    return render(request, "search.html", {
            "authors": followers_qs,
            "query": query,
            "page_type": "followers",
        },
    )

@login_required
def following(request):
    actor = Author.from_user(request.user)

    # Handle POST unfollow
    if request.method == "POST":
        target_id = request.POST.get('author_id')
        target_author = get_object_or_404(Author, id=target_id)

        existing_follow = Follow.objects.filter(actor=actor, object=target_author.id).first()
        if existing_follow:
            existing_follow.delete()

        # Check if following using Follow objects (works for remote)
        is_following = Follow.objects.filter(
            actor=actor,
            object=target_author.id,
            state="ACCEPTED"
        ).exists()
        if is_following:
            # Remove from ManyToMany (for local authors)
            if target_author in actor.following.all():
                actor.following.remove(target_author)

        return redirect(request.META.get('HTTP_REFERER', 'following'))

    # Use Follow objects instead of ManyToMany for remote compatibility
    # The object field is a URLField (FQID string), so we need to handle both exact matches and normalized
    following_follows = Follow.objects.filter(actor=actor, state="ACCEPTED")
    following_ids = []
    following_ids_normalized = []
    for f in following_follows:
        following_ids.append(f.object)  # Raw FQID
        following_ids_normalized.append(normalize_fqid(str(f.object)))  # Normalized
    
    # Try to find authors by both raw and normalized IDs
    following_qs = Author.objects.filter(
        Q(id__in=following_ids) | Q(id__in=following_ids_normalized)
    ).distinct()

    query = request.GET.get('q', '')
    if query:
        following_qs = following_qs.filter(username__icontains=query)  # fixed

    return render(request, "search.html", {
        "authors": following_qs,
        "query": query,
        "page_type": "following",
    })

@login_required
def follow_requests(request):
    actor = Author.from_user(request.user)

    # Handle POST actions: approve or reject
    if request.method == "POST":
        request_id = request.POST.get("follow_id")
        action = request.POST.get("action")
        
        # Normalize actor ID for matching
        actor_id_normalized = normalize_fqid(str(actor.id))
        actor_id_str = str(actor.id).rstrip('/')
        
        # Find follow request - try both normalized and raw IDs
        follow_request = Follow.objects.filter(
            id=request_id
        ).filter(
            Q(object=actor_id_normalized) | Q(object=actor_id_str) | Q(object=actor.id)
        ).first()
        
        if not follow_request:
            return redirect("follow_requests")

        follower_id = follow_request.actor.id  # who requested the follow

        if action == "approve":
            follow_request.state = "ACCEPTED"
            follow_request.save()
            
            # Update following relationship
            if actor not in follow_request.actor.following.all():
                follow_request.actor.following.add(actor)
            
            # Mark inbox item as processed
            inbox_item = Inbox.objects.filter(author=actor, data__id=request_id, processed=False).first()
            if inbox_item:
                inbox_item.processed = True
                inbox_item.save()
            
            #activity = create_accept_follow_activity(actor, request_id)
            #distribute_activity(activity, actor=actor)
            return redirect("follow_requests")

        elif action == "reject":
            follow_request.state = "REJECTED"
            follow_request.save()
            
            # Mark inbox item as processed
            inbox_item = Inbox.objects.filter(author=actor, data__id=request_id, processed=False).first()
            if inbox_item:
                inbox_item.processed = True
                inbox_item.save()
            
            #activity = create_reject_follow_activity(actor, follower_id)
            #distribute_activity(activity, actor=actor)
            return redirect("follow_requests")

    # Only show REQUESTED state - exclude REJECTED and ACCEPTED
    # Normalize actor ID for consistent matching (works for remote)
    actor_id_normalized = normalize_fqid(str(actor.id))
    actor_id_str = str(actor.id).rstrip('/')
    
    follow_requests_qs = Follow.objects.filter(
        state="REQUESTED"  # Only pending requests, not rejected or accepted
    ).filter(
        Q(object=actor_id_normalized) | Q(object=actor_id_str) | Q(object=actor.id)
    ).distinct()
    
    print(f"[DEBUG follow_requests] Found {follow_requests_qs.count()} pending requests for {actor.username}")

    return render(request, "follow_requests.html", {
        "follow_requests": follow_requests_qs
    })

@login_required
def friends(request):
    actor = Author.from_user(request.user)

    # Friends are mutual connections: actor is following them AND they are following actor
    # Use get_friends from distributor which works with Follow objects for both local and remote
    friends_qs = get_friends(actor)

    # Optional: filter by search query
    query = request.GET.get('q', '')
    if query:
        friends_qs = friends_qs.filter(username__icontains=query)

    return render(request, "search.html", {
        "authors": friends_qs,
        "query": query,
        "page_type": "friends",
    })

@login_required
def add_comment(request):
    if request.method == "POST":
        form = CommentForm(request.POST)
        entry_id = request.POST.get("entry_id")

        if not entry_id:
            return redirect(request.META.get("HTTP_REFERER", "stream"))

        if form.is_valid():
            comment = form.save(commit=False)
            comment.id = f"{settings.SITE_URL}/api/comments/{uuid.uuid4()}"
            comment.author = Author.from_user(request.user)
            comment.entry = get_object_or_404(Entry, id=entry_id)
            comment.published = dj_timezone.now()
            comment.save()
            print(f"[DEBUG add_comment] Saved comment:{comment}")

            activity = create_comment_activity(
                author=comment.author,
                entry=comment.entry,
                comment=comment,
            )
            
            distribute_activity(activity, actor=comment.author)

            # Redirect using the saved Entry instance's UUID suffix
            entry = comment.entry
            return redirect("entry_detail", entry_uuid=entry.get_uuid())

    # Fallback for non-POST: just go back to stream
    return redirect("stream")

@login_required
def toggle_like(request):
    """
    This function handles the likes and unlikes process, using a toggle system. 
    """

    # FQID of the object being liked needs to be sent for this to work, otherwise fail gracefully.
    # http://host/api/entries/<uuid> 
    object_fqid = request.POST.get('object')
    if not object_fqid:
        return redirect(request.META.get('HTTP_REFERER', 'stream'))

    # If a foreign user accessed this illegitimately, redirect to login 
    author = Author.from_user(request.user)
    if author is None:
        return redirect('login')

    entry_obj = None
    comment_obj = None

    # Feature Type 1: Attempts to resolve FQID as an Entry 
    try:
        # Case 1: FQID is perfect 
        entry_obj = Entry.objects.get(id=object_fqid)
    except Entry.DoesNotExist:
        try:
            # Case 2: Check endswith because it might be stored as a full URL, and we just got the tail
            entry_obj = Entry.objects.get(id__endswith=object_fqid)
        except Entry.DoesNotExist:
            entry_obj = None

    # Feature Type 1: Attempts to resolve FQID as a Comment 
    if not entry_obj:
        try:
            comment_obj = Comment.objects.get(id=object_fqid)
        except Comment.DoesNotExist:
            try:
                comment_obj = Comment.objects.get(id__endswith=object_fqid)
            except Comment.DoesNotExist:
                comment_obj = None

    target_id = (entry_obj.id if entry_obj else (comment_obj.id if comment_obj else object_fqid))

    with transaction.atomic():
        existing = Like.objects.filter(author=author, object=target_id).first()

        if existing: # UNLIKING LOGIC 
            existing.delete()
            if entry_obj:
                entry_obj.likes.remove(author)

            activity = create_unlike_activity(author, existing.object)
        else: # LIKING LOGIC 
            like_id = f"{settings.SITE_URL.rstrip('/')}/api/likes/{uuid.uuid4()}"
            Like.objects.create(
                id=like_id,
                author=author,    
                object=target_id,  
                published=dj_timezone.now(),
            )

            # If the target is an Entry, add to its many-to-many likes
            if entry_obj:
                entry_obj.likes.add(author)

            activity = create_like_activity(author, target_id) 

    distribute_activity(activity, actor=author)
    return redirect(request.META.get("HTTP_REFERER", "stream"))
    
# * ============================================================
# * Endpoint Receiver Functions
# * ============================================================   

@api_view(['GET'])
def api_follow_requests(request, author_id):
    """Handle the follow requests."""
    try:
        author = Author.objects.get(id=author_id)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)

    # Only return REQUESTED state - exclude REJECTED and ACCEPTED
    follow_requests = Follow.objects.filter(
        object=author.id, 
        state="REQUESTED"
    )
        
    items = [{
        "id": fr.id,
        "type": "Follow",
        "summary": fr.summary,
        "actor": AuthorSerializer(fr.actor).data, 
        "object": fr.object,
        "published": fr.published.isoformat() if fr.published else None,
        "state": fr.state,
    } for fr in follow_requests]

    return Response({"type": "follow-requests", "items": items}, status=200)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_follow_action(request):
    """Handle a user following another user. Works for both local and remote authors."""
    target_id = request.POST.get("author_id")
    
    actor = Author.from_user(request.user)
    if not actor:
        return Response({"error": "User not found"}, status=404)

    # Try to find target - handle both local and remote
    target = Author.objects.filter(id=normalize_fqid(target_id)).first()
    if not target:
        target = Author.objects.filter(id=target_id).first()
    if not target:
        # Try to get or create remote author
        target = get_or_create_foreign_author(target_id)
    
    if not target:
        return Response({"error": "Target author not found"}, status=404)

    if actor == target:
        return Response({"error": "You cannot follow yourself."}, status=400)

    # Normalize target ID for consistent storage
    target_id_normalized = normalize_fqid(str(target.id))
    
    follow, created = Follow.objects.get_or_create(
        actor=actor,
        object=target_id_normalized,
        defaults={"state": "REQUESTED", "published": dj_timezone.now()},
    )
    
    if not created:
        # If follow already exists, update state to REQUESTED if it was REJECTED
        if follow.state == "REJECTED":
            follow.state = "REQUESTED"
            follow.save()


    activity = create_follow_activity(actor, target)
    distribute_activity(activity, actor=actor)

    return Response({"status": "Follow request sent.", "follow_id": follow.id}, status=201)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_accept_follow_action(request):
    """Accept a follow request from another user. Works for both local and remote authors."""
    follow_id = request.POST.get("follow_id")
    print(f"[DEBUG api_accept_follow_action] Accept request: follow_id={follow_id}")
    
    actor = Author.from_user(request.user)
    if not actor:
        return Response({"error": "User not found"}, status=404)
    
    # Normalize actor ID for matching
    actor_id_normalized = normalize_fqid(str(actor.id))
    actor_id_str = str(actor.id).rstrip('/')
    
    # Find follow request - try both normalized and raw IDs
    follow_request = Follow.objects.filter(
        id=follow_id
    ).filter(
        Q(object=actor_id_normalized) | Q(object=actor_id_str) | Q(object=actor.id)
    ).first()
    
    if not follow_request:
        return Response({"error": "Follow request not found"}, status=404)

    if follow_request.state != "REQUESTED":
        return Response({"error": f"Invalid follow request state: {follow_request.state}"}, status=400)

    print(f"[DEBUG api_accept_follow_action] Found follow request: actor={follow_request.actor.username}, object={follow_request.object}, state={follow_request.state}")

    follow_request.state = "ACCEPTED"
    follow_request.published = dj_timezone.now()
    follow_request.save()

    # Update following relationship
    follower = follow_request.actor
    target_id_normalized = normalize_fqid(str(actor.id))
    
    # Add to following ManyToMany (for local authors)
    if actor not in follower.following.all():
        follower.following.add(actor)
        print(f"[DEBUG api_accept_follow_action] Added {actor.username} to {follower.username}'s following")

    # Mark inbox item as processed if it exists
    inbox_item = Inbox.objects.filter(author=actor, data__id=follow_id, processed=False).first()
    if inbox_item:
        inbox_item.processed = True
        inbox_item.save()
        print(f"[DEBUG api_accept_follow_action] Marked inbox item as processed")

    #activity = create_accept_follow_activity(actor, follow_id)
    #distribute_activity(activity, actor=actor)
    
    print(f"[DEBUG api_accept_follow_action] Successfully accepted follow request")

    return Response({"status": "Follow request accepted."}, status=200)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_reject_follow_action(request):
    """Reject a follow request from another user. Works for both local and remote authors."""
    follow_id = request.POST.get("follow_id")
    print(f"[DEBUG api_reject_follow_action] Reject request: follow_id={follow_id}")
    
    actor = Author.from_user(request.user)
    if not actor:
        return Response({"error": "User not found"}, status=404)
    
    # Normalize actor ID for matching
    actor_id_normalized = normalize_fqid(str(actor.id))
    actor_id_str = str(actor.id).rstrip('/')
    
    # Find follow request - try both normalized and raw IDs
    follow_request = Follow.objects.filter(
        id=follow_id
    ).filter(
        Q(object=actor_id_normalized) | Q(object=actor_id_str) | Q(object=actor.id)
    ).first()
    
    if not follow_request:
        return Response({"error": "Follow request not found"}, status=404)

    if follow_request.state != "REQUESTED":
        return Response({"error": f"Invalid follow request state: {follow_request.state}"}, status=400)

    print(f"[DEBUG api_reject_follow_action] Found follow request: actor={follow_request.actor.username}, object={follow_request.object}, state={follow_request.state}")

    follow_request.state = "REJECTED"
    follow_request.published = dj_timezone.now()
    follow_request.save()
    
    print(f"[DEBUG api_reject_follow_action] Updated follow request state to REJECTED")

    # Mark inbox item as processed if it exists
    inbox_item = Inbox.objects.filter(author=actor, data__id=follow_id, processed=False).first()
    if inbox_item:
        inbox_item.processed = True
        inbox_item.save()
        print(f"[DEBUG api_reject_follow_action] Marked inbox item as processed")

    #activity = create_reject_follow_activity(actor, follow_request.actor.id)
    #distribute_activity(activity, actor=actor)
    
    print(f"[DEBUG api_reject_follow_action] Successfully rejected follow request")

    return Response({"status": "Follow request rejected."}, status=200)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_unfollow_action(request):
    """Unfollow a user. Works for both local and remote authors."""
    target_id = request.POST.get("author_id")
    
    actor = Author.from_user(request.user)
    if not actor:
        return Response({"error": "User not found"}, status=404)

    # Try to find target - handle both local and remote
    target = Author.objects.filter(id=normalize_fqid(target_id)).first()
    if not target:
        target = Author.objects.filter(id=target_id).first()
    if not target:
        target = get_or_create_foreign_author(target_id)
    
    if not target:
        return Response({"error": "Target author not found"}, status=404)

    if actor == target:
        return Response({"error": "You cannot unfollow yourself."}, status=400)


    # Remove from ManyToMany (for local authors)
    if target in actor.following.all():
        actor.following.remove(target)

    # Delete Follow objects - normalize IDs for consistent matching
    target_id_normalized = normalize_fqid(str(target.id))
    target_id_str = str(target.id).rstrip('/')
    
    deleted = Follow.objects.filter(actor=actor).filter(
        Q(object=target_id_normalized) | 
        Q(object=target_id_str) | 
        Q(object=target.id)
    ).delete()
    
    #activity = create_unfollow_activity(actor, target.id)
    #distribute_activity(activity, actor=actor)
    
    return Response({"status": f"Unfollowed {target.username}."}, status=200)

@api_view(['GET'])
def list_inbox(request, author_id):
    """
    List all inbox activities for a given author.
    """
    try:
        author = Author.objects.get(id=author_id)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)

    inbox_items = Inbox.objects.filter(author=author)
    serializer = InboxSerializer(inbox_items, many=True)
    return Response(serializer.data)

@csrf_exempt
def inbox_view(request, author_id):

    base = settings.SITE_URL.rstrip("/")
    expected_ids = [
        f"{base}/api/authors/{author_id}",
        f"{base}/authors/{author_id}",
        f"{base}/{author_id}",
    ]

    # FIRST: try to exact match the author (most likely local)
    author = Author.objects.filter(id__in=expected_ids).first()

    # SECOND: try exact match with the author_id as-is (for remote full FQIDs)
    if not author:
        author = Author.objects.filter(id=author_id).first()
        if not author:
            # Try with trailing slash variations
            author = Author.objects.filter(id=author_id.rstrip('/')).first()
            if not author:
                author = Author.objects.filter(id=f"{author_id}/").first()

    # THIRD: try to fallback and fuzzy match for remote slashes/https differences
    if not author:
        author = Author.objects.filter(id__icontains=author_id).first()

    if not author:
        return JsonResponse({"error": "Author not found"}, status=404)

    if request.method == "GET":
        inbox_items = Inbox.objects.filter(author=author).order_by("-received_at")
        return JsonResponse({
            "type": "inbox",
            "author": str(author.id),
            "items": [item.data for item in inbox_items],
        })

    elif request.method == "POST":
        content_type = request.META.get('CONTENT_TYPE', '')
        if 'application/json' not in content_type and 'application/ld+json' not in content_type:
            return JsonResponse({"error": "Invalid Content-Type. Expected application/json or application/ld+json"}, status=400)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            inbox_item = Inbox.objects.create(author=author, data=body)
            
            # Immediately process the inbox to update likes/comments/entries
            # This ensures remote activities are processed right away, not just when the author visits their page
            process_inbox(author)
        except Exception as e:
            return JsonResponse({"error": f"Failed to create/process inbox item: {e}"}, status=500)

        return JsonResponse({"status": "created"}, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)