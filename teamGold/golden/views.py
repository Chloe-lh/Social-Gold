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
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.edit import FormView
from django.utils import timezone as dj_timezone

# IMPORT Django Local
from .decorators import require_author
from .forms import CommentForm, CustomUserForm, EntryForm, ProfileForm

# IMPORT Golden 
from golden.distributor import distribute_activity, process_inbox
from golden.models import (Author, Comment, Entry, EntryImage, Follow, Like, Node, Inbox)
from golden.serializers import *
from golden.services import *
from golden.services import is_local
from golden.activities import ( # Kenneth: If you're adding new activities, please make sure they are uploaded here 
    create_accept_follow_activity,
    create_comment_activity,
    create_delete_entry_activity,
    create_follow_activity,
    create_like_activity,
    create_new_entry_activity,
    create_reject_follow_activity,
    create_unfollow_activity,
    create_unfriend_activity,
    create_update_entry_activity,
    create_unlike_activity,
    create_profile_update_activity,
    create_delete_comment_activity,
)

# IMPORT Miscellaneous
import bleach
import markdown
import requests

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

# ChatGPT, please verify add and verify all HTML Tags, 11-21-2025
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
# * View Functions
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
    user_author = request.user
    process_inbox(user_author)

    follows = Follow.objects.filter(actor=user_author, state='ACCEPTED')
    followed_author_fqids = [f.object for f in follows]

    friends_fqids = []
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

    remote_entries = []
    remote_nodes = Node.objects.filter(is_active=True)
    for node in remote_nodes:

        raw_items = fetch_remote_entries(node)

        for item in raw_items:
            author_data = item.get("author", {})
            remote_author_id = author_data.get("id")

            if not remote_author_id:
                continue

            # only fetch entries from authors the user follows
            is_following = Follow.objects.filter(actor=user_author, object=remote_author_id, state="ACCEPTED").exists()
            if not is_following:
                continue

            entry = sync_remote_entry(item, node)
            if entry:
                remote_entries.append(entry)

    local_entries = Entry.objects.filter(
        (Q(author=user_author) & ~Q(visibility="DELETED")) |
        Q(visibility='PUBLIC') |
        Q(visibility='UNLISTED', author__id__in=followed_author_fqids) |
        Q(visibility='FRIENDS', author__id__in=friends_fqids)
    )
    visible_remote = []

    for e in remote_entries:
        # user is already following this author
        if e.visibility == "PUBLIC":
            visible_remote.append(e)
            continue

        # allowed for followers
        if e.visibility == "UNLISTED":
            visible_remote.append(e)
            continue

        # only if mutual acceptance
        is_mutual = (
            Follow.objects.filter(actor=user_author, object=e.author.id, state="ACCEPTED").exists() and
            Follow.objects.filter(actor=e.author, object=user_author.id, state="ACCEPTED").exists()
        )
        if e.visibility == "FRIENDS" and is_mutual:
            visible_remote.append(e)

    entries = list(local_entries) + visible_remote
    entries.sort(key=lambda x: x.is_posted, reverse=True)

    context = {
        'entries': entries,
        'user_author': user_author,
        'followed_author_fqids': followed_author_fqids,
        'friends_fqids': friends_fqids,
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

    # Heading text
    headings = [
        "Post your thoughts",
        "What’s on your mind?",
        "How are we feeling?",
        "Got something to share?",
        "Drop today’s entry",
        "Even the smallest wins are worth sharing",
        "Anything you want to talk about?",
        "What's up?"
    ]
    entry_heading = random.choice(headings)
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
        entry_id = f"{host}/api/entries/{uuid.uuid4()}"

        user_selected_visibility = request.POST.get("visibility", "PUBLIC")
        if not validate_visibility(user_selected_visibility):
            messages.error(request, "Invalid visibility setting")
            return redirect("stream")

        markdown_content = request.POST.get("content", "")
        html_content = sanitize_markdown_to_html(markdown_content)
        title = escape(request.POST.get("title", ""))

        with transaction.atomic():
            entry = Entry.objects.create(
                id=entry_id,
                author=request.current_author,
                title=title,
                content=html_content,
                contentType="text/html",
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
        messages.success(request, "Entry created successfully!")
        return redirect("stream")

    # FEATURE: EDIT AN EXISTING ENTRY
    if request.method == "POST" and "entry_update" in request.POST:
        primary_key = request.POST.get("entry_update")
        editing_entry = get_object_or_404(Entry, id=primary_key)

        if editing_entry.author.id != request.current_author.id:
            return HttpResponseForbidden("You don't have permission to edit this entry")

        raw_markdown = request.POST.get("content", "")
        user_selected_visibility = request.POST.get("visibility", editing_entry.visibility)

        if not validate_visibility(user_selected_visibility):
            messages.error(request, "Invalid visibility setting")
            return redirect("stream")

        html_content = sanitize_markdown_to_html(raw_markdown)
        title = bleach.clean(request.POST.get("title", editing_entry.title) or editing_entry.title)

        new_images = request.FILES.getlist("images")
        remove_images = request.POST.getlist("remove_images")

        with transaction.atomic():
            # Update entry fields
            editing_entry.title = title
            editing_entry.content = html_content
            editing_entry.visibility = user_selected_visibility
            editing_entry.contentType = "text/html"
            editing_entry.save()

            # Remove selected images
            if remove_images:
                EntryImage.objects.filter(entry=editing_entry, id__in=remove_images).delete()

            # Add new images
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

            # Send update activity for the entry (with attachments if you added that)
            activity = create_update_entry_activity(request.current_author, editing_entry)
            distribute_activity(activity, actor=request.current_author)

        messages.success(request, "Entry updated successfully!")
        # After saving, reset to "new entry" mode
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

        form = EntryForm(instance=editing_entry)
        context.update({
            "editing_entry": editing_entry,
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
        messages.warning(request, "This entry has been deleted.")
        return redirect('stream')
            
    viewer = Author.from_user(request.user)
    process_inbox(viewer)

    if entry.visibility == "FRIENDS":
        # FRIENDS: You will not be able to see the view if you try to access 
        # this post directly through the URL if you ain't friends. 
        if viewer != entry.author and viewer not in entry.author.friends:
            return HttpResponseForbidden("This post is visible to friends only.")
    elif entry.visibility == "UNLISTED":
        # UNLISTED: You will not be able to see the view if you try to access 
        # this post directly through the URL if you don't follow this author
        if viewer != entry.author:
            is_follower = Follow.objects.filter(
                actor=viewer,
                object=entry.author.id,
                state="ACCEPTED"
            ).exists()
            is_friend = viewer in entry.author.friends
            
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

        messages.success(request, "Entry deleted successfully!")
        return redirect('stream')
    
    # FEATURE: EDIT BUTTON CLICKED
    if request.method == "POST" and "entry_edit" in request.POST: # Edit_entry flag for security 
        if entry.author.id != viewer.id:
            return HttpResponseForbidden("You don't have permission to edit this entry")
        return redirect('new_edit_entry_view') 

    # FEATURE: DISPLAY ENTRY AND COMMENTS
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
        # Builds API URL from node.id and will be our primary reference for any future interaction with other nodes.
        api_url =  urljoin(node.id, 'api/authors/') 
        try:
            response = requests.get(
                api_url,
                timeout=5,
                auth=(node.auth_user, node.auth_pass) if node.auth_user else None
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("items", [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching remote authors from {node.id}: {e}")
        return []

    def get_friends_context(author: Author):
        """Inner function to grab the author's friends JSON field specifically for profile.html"""
        friends_qs = author.friends  
        friend_ids = set(f.id for f in friends_qs) 
        return friends_qs, friend_ids

    def sync_github_activity(author):
        """Fetch public GitHub events for the author and create public Entries automatically."""
        if not author.github:
            return

        # Extract username from full URL
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

            # Unique FQID for GitHub entry
            entry_id = f"{author.host}/authors/{author.id}/entries/github-{event_id}"

            # Avoid duplicates
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
                    messages.append(f"[{sha}]({url}): {msg}")
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

            # Convert to HTML
            html_content = markdown.markdown(content_text)

            # Create Entry
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
                is_posted=timezone.now()
            )

    def get_search_authors(author: Author, query: str):
        """Inner function to perform a search queryset specifically for profile.html"""
        results = []
        process_inbox(author)

        following_ids = set(author.following.values_list("id", flat=True))
        
        local_qs = Author.objects.exclude(id=author.id)
        if query: 
            local_qs = local_qs.filter(username__icontains=query)

        for a in local_qs:
            results.append({
                "id": a.id,
                "username": a.username,
                "host": a.host,
                "is_local": True,
                "is_following": a.id in following_ids
            })

        nodes = Node.objects.filter(is_active=True)
        for node in nodes:
            remote_authors = get_remote_authors(node)
            for ra in remote_authors:
                if query.lower() in ra.get("username", "").lower():
                    results.append({
                        "id": ra.get("id"),
                        "username": ra.get("username"),
                        "host": ra.get("host"),
                        "is_local": False,
                        "web": ra.get("web"),
                        "github":ra.get("github"),
                        "profileImage": ra.get("profileImage")
                    })
        return results

    author = Author.from_user(request.user)
    process_inbox(author)
    form = ProfileForm(instance=author)

    if request.method == "GET":
        sync_github_activity(author)

    if request.method == "POST":
        if "follow_id" in request.POST and "action" in request.POST:
            follow_id = request.POST.get("follow_id")
            action = request.POST.get("action")

            if action not in ["approve", "reject"]:
                return HttpResponseBadRequest("Invalid action")

            follow_request = get_object_or_404(Follow, id=follow_id, object=author.id)
            follower_author = follow_request.actor

            if action == "approve":
                follow_request.state = "ACCEPTED"
                follow_request.published = dj_timezone.now()
                follow_request.save()
                follower_author.following.add(author)
                
                activity = create_accept_follow_activity(author, follower_author.id)
                distribute_activity(activity, actor=author)

            elif action == "reject":
                follow_request.state = "REJECTED"
                follow_request.published = dj_timezone.now()
                follow_request.save()

                activity = create_reject_follow_activity(author, follower_author.id)
                distribute_activity(activity, actor=author)

            return redirect("profile")

        if "remove_follower" in request.POST:
            target_id = request.POST.get("remove_follower")
            target = get_object_or_404(Author, id=target_id)
            author.following.remove(author)
            Follow.objects.filter(actor=target, object=author.id).delete()

            # TODO: MAKE THIS ACTIVITY 
            activity = create_remove_follower_activity(author, follower_author.id)
            distribute_activity(activity, actor=author)

            return redirect("profile")
        
        if "unfollow" in request.POST:
            target_id = request.POST.get("unfollow")
            target = get_object_or_404(Author, id=target_id)
            author.following.remove(target)
            Follow.objects.filter(actor=author, object=target.id).delete()

            activity = create_unfollow_activity(author, target_id)
            distribute_activity(activity, actor=author)

            return redirect("profile")
        
        if request.POST.get("action") == "follow":
            target_id = request.POST.get("author_id")

            follow, created = Follow.objects.get_or_create(
                actor=author,
                object=target_id,
                defaults={
                    "id": f"{author.id}/follow/{uuid.uuid4()}",
                    "summary": f"{author.username} wants to follow {target_id}",
                    "published": dj_timezone.now(),
                    "state": "REQUESTED",
                },
            )
            if not created:
                follow.state = "REQUESTED"
                follow.published = dj_timezone.now()
                follow.save()

            activity = create_follow_activity(author, target_id)
            distribute_activity(activity, actor=author)

            return redirect("profile")

        if "remove_friend" in request.POST:
            target_id = request.POST.get("remove_friend")
            target = get_object_or_404(Author, id=target_id)
            author.following.remove(target)
            target.following.remove(author)
            Follow.objects.filter(actor=author, object=target.id).delete()
            Follow.objects.filter(actor=target, object=author.id).delete()

            activity = create_unfriend_activity(author, target_id)
            distribute_activity(activity, actor=author)

            return redirect("profile")

        if "edit_profile" in request.POST:
            form = ProfileForm(request.POST, request.FILES, instance=author)
            if form.is_valid():
                form.save()
                activity = create_profile_update_activity(author)
                distribute_activity(activity, actor=author)

            return redirect("profile")

    friends_qs, friend_ids = get_friends_context(author)
    query = request.GET.get("q", "").strip()
    authors = get_search_authors(author, query)

    for a in authors:
        follow = Follow.objects.filter(actor=author, object=a["id"]).first()
        a["follow_state"] = follow.state if follow else "NONE"
        a["is_following"] = author.following.filter(id=a["id"]).exists()
        a["is_friend"] = str(a["id"]) in friend_ids

    entries = Entry.objects.filter(author=author).exclude(visibility="DELETED").order_by("-published")
    followers = author.followers_set.all()
    following = author.following.all()
    follow_requests = Follow.objects.filter(object=author.id, state="REQUESTED")
    
    # Sanitize description for display
    author.description = sanitize_markdown_to_html(author.description)

    context = {
        "author": author,
        "entries": entries,
        "followers": followers,
        "following": following,
        "follow_requests": follow_requests,
        "friends": friends_qs,
        "form": form,
        "authors": authors,
        "query": escape(query),
    }
    return render(request, "profile.html", context)

@login_required
def public_profile_view(request, author_id):
    """
    View for displaying another author's profile.

    Only shows basic author info (name, github, email, etc.) and list of their entries.
    Tabs and editing are removed.
    """
    author = get_object_or_404(Author, id=author_id)

    # Convert description to HTML
    author.description = sanitize_markdown_to_html(author.description)

    # Get entries for this author
    entries = Entry.objects.filter(author=author).exclude(visibility="DELETED").order_by("-published")

    context = {
        "author": author,
        "entries": entries,
        # We can add sidebar info like GitHub, email, website
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

    followers_qs = actor.followers_set.all()

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

        if target_author in actor.following.all():
            actor.following.remove(target_author)

        return redirect(request.META.get('HTTP_REFERER', 'following'))

    following_qs = actor.following.all()

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
        follow_request = get_object_or_404(Follow, id=request_id)

        follower_id = follow_request.actor.id  # who requested the follow

        if action == "approve":
            activity = create_accept_follow_activity(actor, follower_id)
            distribute_activity(activity, actor=actor)
            return redirect("follow_requests")

        elif action == "reject":
            activity = create_reject_follow_activity(actor, follower_id)
            distribute_activity(activity, actor=actor)
            return redirect("follow_requests")

    follow_requests_qs = Follow.objects.filter(object=actor.id, state="REQUESTED")

    return render(request, "follow_requests.html", {
        "follow_requests": follow_requests_qs
    })

@login_required
def friends(request):
    actor = Author.from_user(request.user)

    # Friends are mutual connections: actor is following them AND they are following actor
    friends_qs = actor.friends

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
def delete_comment(request, comment_id):
    author = Author.from_user(request.user)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.author != author:
        return HttpResponseForbidden("You don't have permission to delete this comment")

    if request.method == "POST":
        # Option A: let inbox processing handle deletion on this node too.
        activity = create_delete_comment_activity(author, comment)
        distribute_activity(activity, actor=author)
        comment.delete()
        # Redirect back to the entry
        entry = comment.entry
        return redirect('entry_detail', entry_uuid=entry.get_uuid())

    # Refuses get delete
    return HttpResponseBadRequest("Invalid request method")

@login_required
def toggle_like(request):
    if request.method != "POST":
        return redirect('stream')

    object_fqid = request.POST.get('object')
    if not object_fqid:
        return redirect(request.META.get('HTTP_REFERER', 'stream'))

    author = Author.from_user(request.user)
    if author is None:
        return redirect('login')

    entry_obj = None
    comment_obj = None

    try:
        entry_obj = Entry.objects.get(id=object_fqid)
    except Entry.DoesNotExist:
        try:
            entry_obj = Entry.objects.get(id__endswith=object_fqid)
        except Entry.DoesNotExist:
            entry_obj = None

    if not entry_obj:
        try:
            comment_obj = Comment.objects.get(id=object_fqid)
        except Comment.DoesNotExist:
            try:
                comment_obj = Comment.objects.get(id__endswith=object_fqid)
            except Comment.DoesNotExist:
                comment_obj = None

    target_id = (
        entry_obj.id if entry_obj else (comment_obj.id if comment_obj else object_fqid)
    )

    with transaction.atomic():
        existing = Like.objects.filter(author=author, object=target_id).first()
        if existing:
            existing.delete()
            if entry_obj:
                entry_obj.likes.remove(author)
            activity = create_unlike_activity(author, target_id)
        else:
            if not Like.objects.filter(author=author, object=target_id).exists():
                like_id = (
                    f"{settings.SITE_URL.rstrip('/')}/api/likes/{uuid.uuid4()}"
                )
                Like.objects.create(
                    id=like_id,
                    author=author,
                    object=target_id,
                    published=dj_timezone.now(),
                )
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
    try:
        author = Author.objects.get(id=author_id)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)

    follow_requests = Follow.objects.filter(object=author.id, state="REQUESTED")

    items = [{
        "id": fr.id,
        "type": "Follow",
        "summary": fr.summary,
        "actor": fr.actor.id,
        "object": fr.object,
        "published": fr.published.isoformat(),
        "state": fr.state,
    } for fr in follow_requests]

    return Response({"type": "follow-requests", "items": items}, status=200)

@api_view(['POST'])
def api_accept_follow(request, follow_id):
    follow_request = get_object_or_404(Follow, id=follow_id)

    follow_request.state = "ACCEPTED"
    follow_request.published = dj_timezone.now()
    follow_request.save()

    acceptor = Author.objects.filter(id=follow_request.object).first()
    follower = follow_request.actor

    if not acceptor or not follower:
        return Response({"error": "Author data missing"}, status=400)

    activity = create_accept_follow_activity(acceptor, follower.id)
    distribute_activity(activity, actor=acceptor)

    return Response({"status": "accepted"}, status=200)

@api_view(['POST'])
def api_reject_follow(request, follow_id):
    follow_request = get_object_or_404(Follow, id=follow_id)

    follow_request.state = "REJECTED"
    follow_request.published = dj_timezone.now()
    follow_request.save()

    acceptor = Author.objects.filter(id=follow_request.object).first()
    follower = follow_request.actor

    if not acceptor or not follower:
        return Response({"error": "Author data missing"}, status=400)

    activity = create_reject_follow_activity(acceptor, follower.id)
    distribute_activity(activity, actor=acceptor)

    return Response({"status": "rejected"}, status=200)

@api_view(['GET'])
def remote_authors_list(request):
    authors = Author.objects.all()
    results = []
    for a in authors:
        results.append({
            "id": a.id,
            "username": a.username,
            "host": a.host,
            "github":a.github,
            "web":a.web,
            "profileImage": a.profileImage.url if a.profileImage else None,
            
        })
    return Response({"type": "authors", "items": results}, status=200)

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
    full_id = f"{settings.SITE_URL}/api/authors/{author_id}"
    try:
        author = Author.objects.get(id=full_id)
    except Author.DoesNotExist:
        return JsonResponse({"error": "Author not found"}, status=404)

    if request.method == "GET":
        inbox_items = Inbox.objects.filter(author=author).order_by("-received_at")
        return JsonResponse(
            {
                "type": "inbox",
                "author": str(author.id),
                "items": [item.data for item in inbox_items],
            }
        )

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            Inbox.objects.create(author=author, data=body)
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to create inbox item: {e}"}, status=500
            )

        return JsonResponse({"status": "created"}, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)