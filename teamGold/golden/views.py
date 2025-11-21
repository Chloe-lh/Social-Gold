# BASE DJANGO 
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.contrib import messages

# REST FRAMEWORKS 
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

# BASE GOLDEN
from golden import models
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node, Inbox
from .forms import CustomUserForm, CommentForm, ProfileForm, EntryList
from golden.serializers import *
from golden.distributor import *
from golden.utils import get_or_create_foreign_author, post_to_remote_inbox, build_accept_activity, fetch_remote_entries, sync_remote_entry, send_new_entry,  send_update_activity

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.generic.edit import FormView
from django.utils import timezone
from django.contrib.auth.views import LoginView
import uuid

# Imports for Entries
from django.contrib.auth import get_user_model
from .decorators import require_author
import markdown
from golden.services import *
# Security
from django.views.decorators.csrf import csrf_exempt

# Imports for AJAX
from django.http import JsonResponse
import json

from urllib.parse import urlparse

# For Website Design
import random
import requests

@login_required
def stream_view(request):
    # current user as Author
    user_author = request.user

    # only a local node uses stream_view
    remote_node = False
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

    remote_node = False
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
        'remote_node': remote_node,
    }

    return render(request, 'stream.html', context)

@login_required
def index(request):
    objects = Author.objects.values()
    print("USERS:")
    for obj in objects:
        print(obj['username']) 
    return render(request, "index.html")

'''
For displaying an error message if a user is not approved yet
'''
class CustomLoginView(LoginView):
    def form_valid(self, form):
        user = form.get_user()
        if not getattr(user, 'is_approved'):
            form.add_error(None, "user has not been approved yet")
            return self.form_invalid(form)
        else:
            return super().form_valid(form)

def signup(request):
    # we want to log users out when they want to sign up
    logout(request)
    # objects = Author.objects.values()
    User = get_user_model()
    objects = User.objects.values()
    print("USERS:")
    for obj in objects:
        print(obj['username'])

    if request.method == "POST":
        # create a form instance and populate it with data from the request
        form = CustomUserForm(request.POST)
        # next_page = request.POST.get('next')
        
        # we don't want to create a user if the inputs are not valid since that can raise errors
        if form.is_valid():
            user = form.save(commit=False)
            user.save()
            #if not next_page:
                #next_page = "/golden/"

            return redirect('profile')     
    else:
        form = CustomUserForm()
        # next_page = request.GET.get('next')

    return render(request, "signup.html", {"form": form})

'''
Uses the database to authenticate if a user is approved or not
Uses Djangos Authentication Backend and will allow user to log in if approved
'''
class ApprovedUserBackend(ModelBackend):
    def user_can_authenticate(self, user):
        is_approved = getattr(user, 'is_approved')
        if isinstance(user, Author) and is_approved:
            return super().user_can_authenticate(user)
        return False # dont allow user to log in if not approved

@api_view(['GET'])
def remote_authors_list(request):
    authors = Author.objects.all()
    results = []
    for a in authors:
        #print(a)
        results.append({
            "id": a.id,
            "username": a.username,
            "host": a.host,
            "github":a.github,
            "web":a.web,
            "profileImage": a.profileImage.url if a.profileImage else None,
            
        })
    #print(results)
    return Response({"type": "authors", "items": results}, status=200)

@login_required
def profile_view(request):
    """
    This function deals the primary logic regarding profile.html.

    Consists of five tabs and one button 
    - Edit Profile Button 
    - Entries Tab 
    - Followers Tab
    - Following Tab
    - Requests Tab
    - Search Tab
    """

    def get_remote_authors(node):
        """
        Fetch all authors from a remote node.
        """
        api_url =  urljoin(node.id, 'api/authors/')  # Build API URL from node.id
        print("TESTY'TEST'SET'SE'", api_url)
        try:
            print("aattemping to send request")
            response = requests.get(
                api_url,
                timeout=5,
                auth=(node.auth_user, node.auth_pass) if node.auth_user else None
            )
            print("remote author get request send. awaiting status", response.status_code)
            print("THIS IS FHE RESPONSE", response.json())
            if response.status_code == 200:
                print("it is a success. now, just need to return it")
                data = response.json()
                return data.get("items", [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching remote authors from {node.id}: {e}")

        return []

    def get_friends_context(author: Author):
        """
        Inner function to grab the author's friends JSON field specifically for profile.html
        """
        friends_qs = author.friends  # this is already a queryset due to the property
        friend_ids = set(f.id for f in friends_qs)  # set of FQIDs
        return friends_qs, friend_ids

    def sync_github_activity(author):
        """
        Fetch public GitHub events for the author and create public Entries automatically.
        """
        if not author.github:
            return  # Skip if no GitHub URL

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
        """
        Inner function to perform a search queryset specifically for profile.html
        """
        results = []
        process_inbox(author)

        following_ids = set(author.following.values_list("id", flat=True))

        # Local authors
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

        # Remote authors
        nodes = Node.objects.filter(is_active=True)

        for node in nodes:
            #print("NODE", node)
            remote_authors = get_remote_authors(node)
            #print("REMOTE AUTHORS", remote_authors)
            for ra in remote_authors:
                #print("RA", ra)
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
    form = ProfileForm(instance=author)

    if request.method == "GET":
        sync_github_activity(author)

    if request.method == "POST":
        if "follow_id" in request.POST and "action" in request.POST:
            follow_id = request.POST.get("follow_id")
            action = request.POST.get("action")

            follow_request = get_object_or_404(Follow, id=follow_id, object=author.id,)
            target_author=follow_request.actor_id

            if action == "approve":
                follow_request.state = "ACCEPTED"
                follow_request.save()

                # Only update the acceptor's following table
                follow_request.actor.following.add(author)
                #follower.save()

            elif action == "reject":
                follow_request.state = "REJECTED"
                follow_request.save()


            #Send decision back to the original actor via inbox
            decision_activity = {
                "type": "process_decision",
                "summary": f"{author.username} has {follow_request.state.lower()}ed your follow request",
                "author": str(author.id),         
                "object": str(target_author), 
                "id": f"{author.id}/follow/{uuid.uuid4()}",
                "state": follow_request.state,
                "published": timezone.now().isoformat(),
                "target_is_local": is_local(target_author),
            }

            distribute_activity(decision_activity, actor=author)
            return redirect("profile")

        if "remove_follower" in request.POST:
            target_id = request.POST.get("remove_follower")
            target = get_object_or_404(Author, id=target_id)
            author.following.remove(target)
            Follow.objects.filter(actor=target, object=author.id).delete()
            return redirect("profile")

        if "unfollow" in request.POST:
            target_id = request.POST.get("unfollow")
            target = get_object_or_404(Author, id=target_id)

            if target.is_local:
                # Local unfollow
                author.following.remove(target)
                Follow.objects.filter(actor=author, object=target.id).delete()
            else:
                # Remote unfollow: send "Undo" Follow activity
                activity = {
                    "type": "Undo",
                    "actor": str(author.id),
                    "object": {
                        "type": "Follow",
                        "actor": str(author.id),
                        "object": target.id
                    }
                }
                push_remote_inbox(target.inbox_url, activity)

            return redirect("profile")

        if request.POST.get("action") == "follow":
            # New POST key for following a remote author
            target_id = request.POST.get("author_id")
            target_author = Author.objects.filter(id=target_id).first()

            # Build ActivityPub Follow activity
            follow_activity = {
                "type": "Follow",
                "summary": f"{author.username} wants to follow you",
                "author": str(author.id),         
                "object": str(target_id), 
                "id": f"{author.id}/follow/{uuid.uuid4()}",
                "state": "REQUESTED",
                "published": timezone.now().isoformat(),
                "target_is_local": is_local(str(target_id)),
            }

            follow, created = Follow.objects.get_or_create(
            actor=author,
            object=target_id,
            defaults={
                'id': f"{author.id}/follow/{uuid.uuid4()}",
                'summary': f"{author.username} wants to follow {target_id}",
                'published': timezone.now(),
                'state': "REQUESTED",
                }
            )

            if not created:
                # Update the follow request timestamp/state
                follow.state = "REQUESTED"
                follow.published = timezone.now()
                follow.save()

            return redirect("profile")
        

        if "remove_friend" in request.POST:
            target_id = request.POST.get("remove_friend")
            target = get_object_or_404(Author, id=target_id)

            # Removes each other from following and followers_info
            author.following.remove(target)
            target.following.remove(author)
            Follow.objects.filter(actor=author, object=target.id).delete()
            Follow.objects.filter(actor=target, object=author.id).delete()

            return redirect("profile")

        if "edit_profile" in request.POST:
            form = ProfileForm(request.POST, request.FILES, instance=author)
            if form.is_valid():
                form.save()
            return redirect("profile")
        
        """
        if request.POST.get("action") == "follow" and "author_id" in request.POST:
            print("test pls work")
            print(request.POST.get("author_id"),request.POST.get("web"),request.POST.get("username"))
            target_id = request.POST.get("author_id")

            parsed = urlparse(target_id)
            remote_host = f"{parsed.scheme}://{parsed.netloc}"
            remote_uuid = target_id.rstrip("/").split("/")[-1]
            target = Author.objects.filter(id=target_id, is_shadow=False).first()

            #target_info  = get_remote_author_profile(remote_host, target_id)
            '''
            we have target author's id
            now we need more info to create a shadow author

            '''
            #we got the target author's id
            print("HERE IS TARGET ID", target_id)
            print("remote host", remote_host)
            print("TARGET OBJECT", target)
            if target:
                # Local follow
                existing = Follow.objects.filter(actor=author, object=target.id).first()
                if not existing:
                    follow_fqid = f"{author.id.rstrip('/')}/follow/{uuid.uuid4()}"
                    Follow.objects.create(
                        id=follow_fqid,
                        actor=author,
                        object=target.id,
                        state="REQUESTED"
                    )
                return redirect("profile")

            '''
            print(" it got to checkpoint1")
            # Find NODE entry for this host
            node = Node.objects.filter(id=remote_host).first()
            print("tf is this node", node)
            if not node:
                print("not supposed to go here")
                messages.error(request, "Remote node not registered.")
                return redirect("profile")
            print(" it got to checkpoint2")
            '''
            '''
            # Create a shadow Author for remote user if not exists
            target, created = Author.objects.get_or_create(
                id=target_id,  # full FQID
                defaults={
                    "username": f"remote-{remote_uuid}",  # ensures uniqueness
                    "name": remote_uuid,                  # used as username
                    "host": remote_host,
                    "is_remote": True,
                    "is_shadow": True,   # mark as shadow
                }
            )
            '''

            # Generate follow FQID
            follow_fqid = f"{author.id.rstrip('/')}/follow/{uuid.uuid4()}"
            print("checkpoint 1", follow_fqid)
            # Store follow request locally
            Follow.objects.create(
                id=follow_fqid,
                actor=author,
                object=target.id if target else target_id,
                state="REQUESTED",
            )

            # Send FOLLOW REQUEST TO REMOTE INBOX
            inbox_url = f"{"https://golden-at1-e84633ad2437.herokuapp.com"}/api/authors/{remote_uuid}/inbox/"
            print("checkpoint2", inbox_url)
            payload = {
                "type": "follow",
                "summary": f"{request.user.username} wants to follow {request.POST.get("username")}",
                "actor": {
                    "type": "author",
                    "id": request.user.id,
                    "host": request.user.host,
                    "username": request.user.username,
                    "github": request.user.github,
                    "profileImage": request.user.profileImage.url if request.user.profileImage else "",
                    "web" : request.user.web


                    
                },
                "object": {
                    "type": "author",
                    "id": request.POST.get("author_id"),
                    "host": request.POST.get("host"),
                    "username": request.POST.get("username"),
                    "github": request.POST.get("github"),
                    "profileImage": request.POST.get("profileImage") if request.POST.get("profileImage") else "",
                    "web": request.POST.get("web")
                }
            }
            print("checkpoint3", payload)
            try:

                resp = requests.post(
                    inbox_url,
                    json=payload,
                    timeout=15,
                    auth=("admin", "password2025")
                )
                print("REMOTE FOLLOW RESPONSE:", resp.status_code, resp.text)
            except Exception as e:
                print("ERROR SENDING REMOTE FOLLOW:", e)

            return redirect("profile")
        """

    friends_qs, friend_ids = get_friends_context(author)
    query = request.GET.get("q", "").strip()
    authors = get_search_authors(author, query)

    for a in authors:
        if a.get("is_local"):
            # Django Author object
            follow = Follow.objects.filter(actor=author, object=a["id"]).first()
            a["follow_state"] = follow.state if follow else "NONE"
            a["is_following"] = author.following.filter(id=a["id"]).exists()
            a["is_friend"] = str(a["id"]) in friend_ids
        else:
            # Remote authors — assume not following/friends by default
            a["follow_state"] = "NONE"
            a["is_following"] = False
            a["is_friend"] = False 

    entries = Entry.objects.filter(author=author).exclude(visibility="DELETED").order_by("-published")
    followers = author.followers_set.all()
    following = author.following.all()
    follow_requests = Follow.objects.filter(object=author.id, state="REQUESTED")
    author.description = markdown.markdown(author.description)

    context = {
        "author": author,
        "entries": entries,
        "followers": followers,
        "following": following,
        "follow_requests": follow_requests,
        "friends": friends_qs,
        "form": form,
        "authors": authors,
        "query": query,
    }
    #print(authors)
    return render(request, "profile.html", context)

FOLLOW_STATE_CHOICES = ["REQUESTED", "ACCEPTED", "REJECTED"]

@login_required
def public_profile_view(request, author_id):
    """
    View for displaying another author's profile.

    Only shows basic author info (name, github, email, etc.) and list of their entries.
    Tabs and editing are removed.
    """

    # Get author
    author = get_object_or_404(Author, id=author_id)

    # Convert description to HTML
    author.description = markdown.markdown(author.description)

    # Get entries for this author
    entries = Entry.objects.filter(author=author).exclude(visibility="DELETED").order_by("-published")

    context = {
        "author": author,
        "entries": entries,
        # We can add sidebar info like GitHub, email, website
    }

    return render(request, "public_profile.html", context)

"""
def search_authors(request):
    actor = Author.from_user(request.user)

    # Handle POST follow requests
    if request.method == "POST":
        target_id = request.POST.get('author_id')
        target_author = get_object_or_404(Author, id=target_id)

        # Check if a follow object already exists
        follow, created = Follow.objects.get_or_create(
            actor=actor,
            object=target_author.id,
            defaults={
                'id': f"{actor.id}/follow/{uuid.uuid4()}",
                'summary': f"{actor.username} wants to follow {target_author.username}",
                'published': timezone.now(),
                'state': "REQUESTED",
            }
        )

        if not created:
            # Reset state to REQUESTED if already exists
            follow.state = "REQUESTED"
            follow.published = timezone.now()
            follow.save()

        return redirect(request.META.get('HTTP_REFERER', 'search_authors'))

    # GET request: display authors
    query = request.GET.get('q', '')
    if query:
        authors = Author.objects.filter(username__icontains=query)
    else:
        authors = Author.objects.all()

    authors = authors.exclude(id=actor.id)

    # Attach follow state for template
    for author in authors:
        f = Follow.objects.filter(actor=actor, object=author.id).first()
        author.follow_state = f.state if f else None

    return render(request, "search.html", {
        "authors": authors,
        "query": query,
        "page_type": "search_authors",
        "active_tab": "search",
    })
"""

@login_required
def followers(request):
    actor = Author.from_user(request.user)

    # Handle POST remove follower
    if request.method == "POST":
        follower_id = request.POST.get('author_id')
        follower = get_object_or_404(Author, id=follower_id)

        follower.following.remove(actor)
        follower.save()

        # Delete Follow object if exists
        Follow.objects.filter(actor=follower, object=actor.id).delete()
        return redirect(request.META.get('HTTP_REFERER', 'followers'))

    # GET request: show followers
    followers_qs = actor.followers_set.all()
    # authors = Author.objects.filter(id__in=followers_ids)

    query = request.GET.get('q', '')
    if query:
        # authors = authors.filter(username__icontains=query)
        followers_qs = followers_qs.filter(username__icontains=query)

    return render(request, "search.html", {
        "authors": authors,
        "query": query,
        "page_type": "followers",
    })


@login_required
def following(request):
    actor = Author.from_user(request.user)

    # Handle POST unfollow
    if request.method == "POST":
        target_id = request.POST.get('author_id')
        target_author = get_object_or_404(Author, id=target_id)

        # Delete Follow object if exists
        existing_follow = Follow.objects.filter(actor=actor, object=target_author.id).first()
        if existing_follow:
            existing_follow.delete()

        # Remove target from actor.following (ManyToMany)
        if target_author in actor.following.all():
            actor.following.remove(target_author)
            #actor.save(update_fields=["following"])

        return redirect(request.META.get('HTTP_REFERER', 'following'))

    # GET request: show following
    following_qs = actor.following.all()

    query = request.GET.get('q', '')
    if query:
        following_qs = authors.filter(username__icontains=query)

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

        if action == "approve":
            follow_request.state = "ACCEPTED"
            follow_request.save()
            follower_author = follow_request.actor
            follower_author.following.add(actor)
            follower_author.save()

        elif action == "reject":
            follow_request.state = "REJECTED"
            follow_request.save()

        return redirect("follow_requests")

    # GET: display all incoming follow requests
    follow_requests = Follow.objects.filter(object=actor.id, state="REQUESTED")

    return render(request, "follow_requests.html", {
        "follow_requests": follow_requests
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
        "page_type": "friends",  # Used in template to hide buttons
    })
'''
    minimal comment form POSTs for local comments
    expects CommentForm object from HTML in Entry_details
'''
@login_required
def add_comment(request):
    if request.method == "POST": # user clicks add comment button in entry_details
        form = CommentForm(request.POST)
        # get entry id from html
        entry_id = request.POST.get('entry_id')
        if form.is_valid():
            comment = form.save(commit=False) # dont save unless user presses add comment
            # create a unique id/URL for each comment
            comment.id = f"{settings.SITE_URL}/api/Comment/{uuid.uuid4()}"
            comment.author = Author.from_user(request.user)
            comment.entry = get_object_or_404(Entry, id=entry_id)
            comment.published = timezone.now()
            comment.save()
            # Redirect using the saved Entry instance's UUID suffix
            entry = comment.entry
            return redirect('entry_detail', entry_uuid=entry.get_uuid())


@login_required
def toggle_like(request):
    """ Minimal like/unlike form POSTs.

    Expects POST field `object` containing the target object's FQID
    (Entry.id or Comment.id). Redirects back to the referring page.
    """
    if request.method != 'POST':
        return redirect('stream')

    object_fqid = request.POST.get('object')
    if not object_fqid:
        return redirect(request.META.get('HTTP_REFERER', 'stream'))

    author = Author.from_user(request.user)
    if author is None:
        return redirect('login')

     # Try to resolve Entry first (full FQID or suffix). If not Entry, check Comment.
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

    # Toggle in a transaction to keep Like rows and Entry.likes in sync
    with transaction.atomic():
        existing = Like.objects.filter(author=author, object=(entry_obj.id if entry_obj else (comment_obj.id if comment_obj else object_fqid))).first()
        if existing:
            existing.delete()
            if entry_obj:
                entry_obj.likes.remove(author)
            # For comments we don't have a comment_obj.likes; counts come from Like table.
        else:
            existing = Like.objects.filter(author=author, object=(entry_obj.id if entry_obj else (comment_obj.id if comment_obj else object_fqid))).first()
            if not existing:
                like_id = f"{settings.SITE_URL.rstrip('/')}/api/Like/{uuid.uuid4()}"
                Like.objects.create(id=like_id, author=author, object=(entry_obj.id if entry_obj else (comment_obj.id if comment_obj else object_fqid)), published=timezone.now())
                if entry_obj:
                    entry_obj.likes.add(author)

    return redirect(request.META.get('HTTP_REFERER', 'stream'))
    

''' 
view displays the entry as well as comments below it
'''
#! TODO: WIP
@login_required
def entry_detail(request, entry_uuid):
    try:
        entry = Entry.objects.get(id=entry_uuid)
    except Entry.DoesNotExist:
        entry = get_object_or_404(Entry, id__endswith=str(entry_uuid))
    
    if entry.visibility == 'DELETED':
        # TODO: entry deleted page?
        # return Response({"error": "Entry Deleted Permanently"}, status=410)
        
        # If the entry is deleted, we don't want to allow users to bug into the entry page with the url
        return redirect('stream')
    
    viewer = Author.from_user(request.user)
    # Enforce visibility (deny if FRIENDS-only and viewer isn't allowed)
    # VISIBILITY CHECK (NEW VERSION)
    if entry.visibility == "FRIENDS":
        if viewer != entry.author and viewer not in entry.author.friends:
            return HttpResponseForbidden("This post is visible to friends only.")

    # Fetch comments for the entry (all comments if viewer is allowed)
    comments_qs = entry.comment.select_related('author').order_by('published')

    serialized_comments = CommentSerializer(comments_qs, many=True).data
    entry_comments = { entry.id: serialized_comments }

    context = {
        'entry': entry,
        'comments': comments_qs,
        'comment_form': CommentForm(),
        'entry_comments_json': json.dumps(entry_comments),
    }
    return render(request, 'entry_detail.html', context)

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
        return JsonResponse({
            "type": "inbox",
            "author": str(author.id),
            "items": [item.data for item in inbox_items]
        })

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        Inbox.objects.create(
            id=f"{settings.SITE_URL}/api/inbox/{uuid.uuid4()}",
            author=author,
            data=data
        )
        return JsonResponse({"status": "created"}, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)

"""
@api_view(['POST'])
def inbox(request, author_id):

    Remote nodes call this endpoint.
    We:
    1. identify the inbox owner
    2. validate + normalize the activity
    3. store the activity in the inbox
    4. run local handlers (create/update/delete/comment/like/follow)

    print("IT GOT TO INBOX?!")
    try:
        host = request.build_absolute_uri('/')  # "https://node1/"
        full_author_id = f"{host}api/authors/{author_id}/"
        author = Author.objects.get(id=full_author_id)

    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)
    
    data = request.data
    print("this is recieving data", data)
    activity_type = data.get("type", "").lower()

    dispatch_table = {
        "entry": handle_create,
        "create": handle_create,
        "post": handle_create,
        "update": handle_update,
        "delete": handle_delete,
        "like": handle_like,
        "comment": handle_comment,
        "follow": handle_follow,
        "follow-back": handle_follow_back,
    }

    if activity_type not in dispatch_table:
        return Response({"error": f"Unsupported type {activity_type}"}, status=400)

    Inbox.objects.create(author=author, data=data)

    return dispatch_table[activity_type](data, author)
    
def handle_update(data, author):

    Processes the remote update activity for an Entry.
    Handels user stories #22 and #35 

    object_id = data.get("object", {})

    if not isinstance(object_id, dict):
        return Response({"error": "Invalid update object"}, status=400)

    entry_id = object_id.get("id")
    if not entry_id:
        return Response({"error": "Missing object.id in update"}, status=400)

    # Finds an existing Entry to prevent the creation of new entries since this is editing (PUT).
    try:
        entry = Entry.objects.get(id=entry_id)
    except Entry.DoesNotExist:
        return Response({"error": "Entry not found"}, status=404)

    # Update fields that remote nodes are allowed to overwrite
    updated = False

    if "title" in object_id:
        entry.title = object_id["title"]
        updated = True

    if "content" in object_id:
        entry.content = object_id["content"]
        updated = True

    if "contentType" in object_id:
        entry.contentType = object_id["contentType"]
        updated = True

    if "visibility" in object_id:
        entry.visibility = object_id["visibility"]
        updated = True

    if updated:
        entry.is_updated = timezone.now()
        entry.save()

    return Response({"status": "Entry updated"}, status=200)

def handle_create(data, author):
    object_id = data.get("object", {})
    serializer = EntryInboxSerializer(data=object_id, context={'author': author})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

def handle_like(data,author):
    serializer = LikeInboxSerializer(data=data, context={'author': author})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

def handle_comment(data,author):
    serializer = CommentsInfoSerializer(data=data, context={'author': author})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

def handle_follow(data, author):
    actor_data = data.get("actor")
    object_id = data.get("object")

    if not actor_data or not object_id:
        return Response({"error": "Follow activity missing actor or object"}, status=400)

    if object_id != author.id:
        return Response({"error": "Follow target does not match inbox author"}, status=400)

    # Parse remote author info
    remote_id = actor_data.get("id")
    remote_display = actor_data.get("username", "Unknown")
    remote_host = actor_data.get("host")

    if not remote_id or not remote_host:
        return Response({"error": "Invalid remote actor format"}, status=400)

    # Create or update remote author locally
    remote_author, created = Author.objects.get_or_create(
        id=remote_id,
        defaults={
            "username": remote_display,
            "host": remote_host,
            "github": actor_data.get("github", ""),
            "profileImage": actor_data.get("profileImage", "")
        }
    )

    # Check if follow already exists
    existing = Follow.objects.filter(
        actor=remote_author, 
        object= author
    ).first()

    if existing:
        return Response({"status": "Already following"}, status=200)

    # Create follow relationship
    follow_request = Follow.objects.create(
        actor=remote_author,
        object=author
    )

    serializer = FollowSerializer(follow_request)
    return Response(serializer.data, status=201)
"""
@login_required
@require_author 
def new_post(request):
    """
    @require_author is linked with deorators.py to ensure user distinction
    """
    if request.current_author is None:
        return redirect('signup')
    
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

    context = {}
    form = EntryList()
    editing_entry = None # because by default, users are not in editing mode 
    entries = Entry.objects.exclude(visibility="DELETED").order_by('-is_posted')
    context['entries'] = entries
    context['entry_heading'] = entry_heading

    # FEATURE POST AN ENTRY
    if request.method == "POST" and "entry_post" in request.POST:
        host = settings.SITE_URL.rstrip("/")
        entry_id = f"{host}/api/entries/{uuid.uuid4()}"

        # Markdown conversion 
        markdown_content = request.POST['content']
        html_content = markdown.markdown(markdown_content)

        with transaction.atomic(): 
            entry = Entry.objects.create(
                id=entry_id,
                author=request.current_author,
                content=html_content,
                visibility=request.POST.get('visibility', 'PUBLIC')
            )
        
        images = request.FILES.getlist('images')
        for idx, image in enumerate(images):
            EntryImage.objects.create(
                entry=entry, image=image, order=idx)
        
        send_new_entry(entry)
        return redirect('new_post')
    
    # FEATURE DELETE AN ENTRY 
    if request.method == "POST" and "entry_delete" in request.POST:
        primary_key = request.POST.get('entry_delete')
        entry = Entry.objects.get(id=primary_key)

        # also for testing purposes 
        if entry.author.id != request.current_author.id:
            return HttpResponseForbidden("This isn't yours")

        entry.visibility = 'DELETED'
        entry.save()
        return redirect('new_post')
    
    # FEATURE UPDATE AN EDITED ENTRY
    if request.method == "POST" and "entry_update" in request.POST:
        primary_key = request.POST.get("entry_update")
        editing_entry = get_object_or_404(Entry, id=primary_key)

        # for testing 
        if editing_entry.author.id != request.current_author.id:
            return HttpResponseForbidden("No editing")
        
        raw_md = request.POST.get("content", "")
        visibility = request.POST.get("visibility", editing_entry.visibility)

        # difference between adding a new image and remove an image 
        new_images = request.FILES.getlist("images")
        remove_images = request.POST.getlist("remove_images")
        remove_ids = []
        for x in remove_images:
            try:
                remove_ids.append(int(x))
            except (TypeError, ValueError):
                pass 

        with transaction.atomic():
            editing_entry.content = markdown.markdown(raw_md)
            editing_entry.visibility = visibility
            editing_entry.contentType = "text/html"
            editing_entry.save()
            
            send_update_activity(editing_entry)


            if remove_ids:
                EntryImage.objects.filter(entry=editing_entry, id__in=remove_ids).delete()

            # Append any newly uploaded images, preserving order
            if new_images:
                current_max = editing_entry.images.count()
                for idx, f in enumerate(new_images):
                    EntryImage.objects.create(
                        entry=editing_entry,
                        image=f,
                        order=current_max + idx
                    )

        context = {}
        context['form'] = EntryList()  
        context['editing_entry'] = None 
        context['entries'] = Entry.objects.exclude(visibility="DELETED").select_related("author")
        context['comment_form'] = CommentForm()
        
        return render(request, "new_post.html", context)
        #return render(request, "new_post.html", context | {'entries': entries})

    # FEATURE EDIT BUTTON CLICKED 
    if request.method == "POST" and "entry_edit" in request.POST:
        primary_key = request.POST.get('entry_edit')
        editing_entry = get_object_or_404(Entry, id=primary_key)

        form = EntryList(instance=editing_entry)
        context["editing_entry"] = editing_entry
        context["form"] = form
        context["entries"] = Entry.objects.select_related("author").filter(~Q(visibility='DELETED'))
        return render(request, "new_post.html", context | {'entries': entries})

    context['form'] = form 
    context["editing_entry"] = editing_entry
    # context["entries"] = Entry.objects.select_related("author").all()
 
    return render(request, "new_post.html", context | {'entries': entries})