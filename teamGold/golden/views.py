# BASE DJANGO 
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

# REST FRAMEWORKS 
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

# BASE GOLDEN
from golden import models
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow, Node
from .forms import CustomUserForm, CommentForm, ProfileForm, EntryList
from golden.serializers import CommentSerializer, EntryInboxSerializer, LikeInboxSerializer, CommentsInfoSerializer, FollowRequestInboxSerializer
from golden.utils import get_or_create_foreign_author, post_to_remote_inbox, build_accept_activity

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

# Security
from django.views.decorators.csrf import csrf_exempt

# Imports for AJAX
from django.http import JsonResponse
import json

# For Website Design
import random
import requests

# TODO: Do we still need this?
@login_required
def stream_view(request):
    # Get the Author object for the logged-in user
    user_author = request.user

    # only a local node uses stream_view
    remote_node = False

    # Get all accepted follows (authors this user follows)
    follows = Follow.objects.filter(actor=user_author, state='ACCEPTED')
    followed_author_fqids = [f.object for f in follows]

    # Determine authors who are "friends" (mutual follows)
    friends_fqids = []
    for f in follows:
        try:
            # Check if the followed author also follows the user
            reciprocal = Follow.objects.get(actor__id=f.object, object=user_author.id, state='ACCEPTED')
            friends_fqids.append(f.object)
        except Follow.DoesNotExist:
            continue

    # Query entries according to visibility rules

    entries = Entry.objects.filter(
        (Q(author=user_author) & ~Q(visibility="DELETED")) |
        Q(visibility='PUBLIC') |  # Public entries: everyone can see
        Q(visibility='UNLISTED', author__id__in=followed_author_fqids) |  # Unlisted: only followers
        Q(visibility='FRIENDS', author__id__in=friends_fqids)  # Friends-only: only friends
    ).order_by('-is_updated', '-published')  # Most recent first

    # Prepare context for the template
    context = {
        'entries': entries,
        'user_author': user_author,
        'followed_author_fqids': followed_author_fqids,
        'friends_fqids': friends_fqids,
        'comment_form' : CommentForm(),
        # 'entry_comments_json': json.dumps(entry_comments),
        'remote_node':remote_node,
    }

    # Render the stream page extending base.html
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
        results.append({
            "id": a.id,
            "displayName": a.username,
            "host": a.host,
        })
    return Response({"type": "authors", "items": results})

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
        api_url = f"{node.id}/api/authors/"  # Build API URL from node.id

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
        """
        Inner function to grab the author's friends JSON field specifically for profile.html
        """
        friends_qs = author.friends  # this is already a queryset due to the property
        friend_ids = set(f.id for f in friends_qs)  # set of FQIDs
        return friends_qs, friend_ids

    def get_search_authors(author: Author, query: str):
        """
        Inner function to perform a search queryset specifically for profile.html
        """
        results = []

        # Local authors
        local_qs = Author.objects.exclude(id=author.id)
        if query:
            local_qs = local_qs.filter(username__icontains=query)

        for a in local_qs:
            results.append({
                "id": a.id,
                "username": a.username,
                "host": a.host,
                "is_local": True
            })

        # Remote authors
        nodes = Node.objects.filter(is_active=True)#.exclude(id=author.host)  # exclude local node

        for node in nodes:
            remote_authors = get_remote_authors(node)
            for ra in remote_authors:
                if query.lower() in ra.get("displayName", "").lower():
                    results.append({
                        "id": ra.get("id"),
                        "username": ra.get("displayName"),
                        "host": ra.get("host"),
                        "is_local": False
                    })
        return results

    author = Author.from_user(request.user)
    form = ProfileForm(instance=author)

    if request.method == "POST":
        if "follow_id" in request.POST and "action" in request.POST:
            follow_id = request.POST.get("follow_id")
            action = request.POST.get("action")
            follow_request = get_object_or_404(Follow, id=follow_id, object=author.id)

            if action == "approve":
                follow_request.state = "ACCEPTED"
                follow_request.save()

                follower = follow_request.actor
                follower.following.add(author)
                follower.save()

            elif action == "reject":
                follow_request.state = "REJECTED"
                follow_request.save()

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
            author.following.remove(target)
            Follow.objects.filter(actor=author, object=target.id).delete()
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
        
        if request.POST.get("action") == "follow" and "author_id" in request.POST:
            target_id = request.POST.get("author_id")
            target = get_object_or_404(Author, id=target_id)

            # Checks if a follow already exists
            existing = Follow.objects.filter(
                actor=author,
                object=target.id,
            ).first()

            if not existing:
                # Builds a UNIQUE follow request ID (FQID)
                follow_id = f"{author.id.rstrip('/')}/follow/{uuid.uuid4()}"
                # Example output:
                # https://golden.com/author/123/follow/9f1f247b-e8cf-4e91-8a61-e0c84bd2e4d1

                Follow.objects.create(
                    id=follow_id,
                    actor=author,
                    object=target.id,
                    state="REQUESTED",
                )
            return redirect("profile")   
    else:
        form = ProfileForm(instance=author)

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

    entries = Entry.objects.filter(Q(author=author) & ~Q(visibility='DELETED')).order_by("-published")
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

    return render(request, "profile.html", context)

FOLLOW_STATE_CHOICES = ["REQUESTED", "ACCEPTED", "REJECTED"]

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


@api_view(['POST'])
def inbox(request, author_id):
    try:
        host = request.build_absolute_uri('/')  # "https://node1/"
        full_author_id = f"{host}api/authors/{author_id}/"
        author = Author.objects.get(id=full_author_id)
    except Author.DoesNotExist:
        return Response({"error": "Author not found"}, status=404)
    
    data = request.data
    activity_type = data.get("type", "").lower()

    if activity_type == "create":
        return handle_create(data, author)
    elif activity_type == "like":
        return handle_like(data, author)
    elif activity_type == "comment":
        return handle_comment(data, author)
    elif activity_type == "follow":
        return handle_follow(data, author)
    elif activity_type == "update":
        return handle_update(data, author)
    else:
        return Response({"error": "Unsupported type"}, status=400)
    
def handle_update(data, author):
    """
    Processes the remote update activity for an Entry.
    Handels user stories #22 and #35 
    """
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
        # So that admin can still see what was deleted
        if entry.visibility == "DELETED":
            entry.content = ""

    if updated:
        entry.is_updated = timezone.now()
        entry.save()

    return Response({"status": "Entry updated"}, status=200)


def handle_create(data, author):
    serializer = EntryInboxSerializer(data=data, context={'author': author})
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
    serializer = FollowRequestInboxSerializer(data=data, context={'author': author})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

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
    entries = Entry.objects.filter(Q(author=request.current_author) & ~Q(visibility='DELETED')).order_by('-is_posted')
    context['entries'] = entries
    context['entry_heading'] = entry_heading

    # FEATURE POST AN ENTRY
    if request.method == "POST" and "entry_post" in request.POST:
        entry_id = f"https://node1.com/api/entries/{uuid.uuid4()}"  #****** we need to change this to dynamically get the node num

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
        context['entries'] = Entry.objects.select_related("author").filter(~Q(visibility='DELETED'))
        context['comment_form'] = CommentForm()
        
        return render(request, "new_post.html", context | {'entries': entries})

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