# BASE DJANGO 
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

# REST FRAMEWORKS 
import markdown
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, generics


# BASE GOLDEN
from golden import models
from golden.models import Entry, EntryImage, Author, Comment, Like, Follow
from .forms import CustomUserForm, CommentForm, ProfileForm, EntryList
from golden.serializers import CommentSerializer

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.generic.edit import FormView
from django.utils import timezone
from django.contrib.auth.views import LoginView
import uuid

# view decorator
from django.views.decorators.http import require_POST

# Imports for entries
from django.contrib.auth import get_user_model
from .decorators import require_author
import markdown

#secuirity
from django.views.decorators.csrf import csrf_exempt

#imports for AJAX
from django.http import JsonResponse
import json

# For Website Design
import random

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

    # etermine authors who are "friends" (mutual follows)
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


# @login_required
# @require_author 
# def home(request):
#     """
#     @require_author is linked with deorators.py to ensure user distinction
#     """
#     if request.current_author is None:
#         return redirect('signup')
    
#     context = {}
#     form = EntryList()
#     editing_entry = None # because by default, users are not in editing mode 
#     entries = Entry.objects.all().order_by('-is_posted')
#     context['entries'] = entries

#     # FEATURE POST AN ENTRY
#     if request.method == "POST" and "entry_post" in request.POST:
#         entry_id = f"{settings.SITE_URL}/api/entries/{uuid.uuid4()}"  #****** we need to change this to dynamically get the node num

#         # Markdown conversion 
#         markdown_content = request.POST['content']
#         html_content = markdown.markdown(markdown_content)

#         with transaction.atomic(): 
#             entry = Entry.objects.create(
#                 id=entry_id,
#                 author=request.current_author,
#                 content=html_content,
#                 visibility=request.POST.get('visibility', 'PUBLIC')
#             )
        

#         images = request.FILES.getlist('images')
#         for idx, image in enumerate(images):
#             EntryImage.objects.create(
#                 entry=entry, image=image, order=idx)
                    
#         return redirect('home')
    
#     # FEATURE DELETE AN ENTRY 
#     if request.method == "POST" and "entry_delete" in request.POST:
#         primary_key = request.POST.get('entry_delete')
#         entry = Entry.objects.get(id=primary_key)

#         # also for testing purposes 
#         if entry.author.id != request.current_author.id:
#             return HttpResponseForbidden("This isn't yours")

#         entry.delete()
#         return redirect('home')
    
#     # FEATURE UPDATE AN EDITED ENTRY
#     if request.method == "POST" and "entry_update" in request.POST:
#         primary_key = request.POST.get("entry_update")
#         editing_entry = get_object_or_404(Entry, id=primary_key)

#         # for testing 
#         if editing_entry.author.id != request.current_author.id:
#             return HttpResponseForbidden("No editing")
        
#         raw_md = request.POST.get("content", "")
#         visibility = request.POST.get("visibility", editing_entry.visibility)

#         # difference between adding a new image and remove an image 
#         new_images = request.FILES.getlist("images")
#         remove_images = request.POST.getlist("remove_images")
#         remove_ids = []
#         for x in remove_images:
#             try:
#                 remove_ids.append(int(x))
#             except (TypeError, ValueError):
#                 pass 

#         with transaction.atomic():
#             editing_entry.content = markdown.markdown(raw_md)
#             editing_entry.visibility = visibility
#             editing_entry.contentType = "text/html"
#             editing_entry.save()

#             if remove_ids:
#                 EntryImage.objects.filter(entry=editing_entry, id__in=remove_ids).delete()

#             # Append any newly uploaded images, preserving order
#             if new_images:
#                 current_max = editing_entry.images.count()
#                 for idx, f in enumerate(new_images):
#                     EntryImage.objects.create(
#                         entry=editing_entry,
#                         image=f,
#                         order=current_max + idx
#                     )

#         context = {}
#         context['form'] = EntryList()  
#         context['editing_entry'] = None 
#         context['entries'] = Entry.objects.select_related("author").all()
#         context['comment_form'] = CommentForm()
#         return render(request, "home.html", context | {'entries': entries})

#     # FEATURE EDIT BUTTON CLICKED 
#     if request.method == "POST" and "entry_edit" in request.POST:
#         primary_key = request.POST.get('entry_edit')
#         editing_entry = get_object_or_404(Entry, id=primary_key)

#         form = EntryList(instance=editing_entry)
#         context["editing_entry"] = editing_entry
#         context["form"] = form
#         context["entries"] = Entry.objects.select_related("author").all()
#         return render(request, "home.html", context | {'entries': entries})

#     context['form'] = form 
#     context["editing_entry"] = editing_entry
#     # context["entries"] = Entry.objects.select_related("author").all()
 

#     return render(request, "home.html", context | {'entries': entries})

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
            user.id = f"{settings.SITE_URL}/api/authors/{uuid.uuid4()}"
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

@login_required
def profile_view(request):
    author = Author.from_user(request.user)

    if request.method == "POST":
        # 1️⃣ Approve / Reject follow requests
        if "follow_id" in request.POST and "action" in request.POST:
            follow_id = request.POST.get("follow_id")
            action = request.POST.get("action")
            follow_request = get_object_or_404(Follow, id=follow_id, object=author.id)

            if action == "approve":
                follow_request.state = "ACCEPTED"
                follow_request.save()

                follower = follow_request.actor
                followers_info = author.followers_info or {}
                followers_info[str(follower.id)] = follower.username
                author.followers_info = followers_info
                author.save(update_fields=["followers_info"])

                follower.following.add(author)
                follower.save()

                author.update_friends()
                follower.update_friends()

            elif action == "reject":
                follow_request.state = "REJECTED"
                follow_request.save()

            return redirect("profile")

        if "remove_follower" in request.POST:
            target_id = request.POST.get("remove_follower")
            target = get_object_or_404(Author, id=target_id)
            followers_info = author.followers_info or {}
            followers_info.pop(str(target.id), None)
            author.followers_info = followers_info
            author.save(update_fields=["followers_info"])
            Follow.objects.filter(actor=target, object=author.id).delete()
            target.update_friends()
            author.update_friends()
            return redirect("profile")

        if "unfollow" in request.POST:
            target_id = request.POST.get("unfollow")
            target = get_object_or_404(Author, id=target_id)
            author.following.remove(target)
            Follow.objects.filter(actor=author, object=target.id).delete()
            target.update_friends()
            author.update_friends()
            return redirect("profile")

        if "remove_friend" in request.POST:
            target_id = request.POST.get("remove_friend")
            target = get_object_or_404(Author, id=target_id)

            # Remove each other from following and followers_info
            author.following.remove(target)
            target.following.remove(author)
            followers_info = author.followers_info or {}
            followers_info.pop(str(target.id), None)
            author.followers_info = followers_info
            author.save(update_fields=["followers_info"])
            target_info = target.followers_info or {}
            target_info.pop(str(author.id), None)
            target.followers_info = target_info
            target.save(update_fields=["followers_info"])

            author.update_friends()
            target.update_friends()
            Follow.objects.filter(actor=author, object=target.id).delete()
            Follow.objects.filter(actor=target, object=author.id).delete()

            return redirect("profile")

        if "edit_profile" in request.POST:
            form = ProfileForm(request.POST, request.FILES, instance=author)
            if form.is_valid():
                form.save()
            return redirect("profile")

    else:
        form = ProfileForm(instance=author)

    # --- BUILD CONTEXT DATA ---
    entries = Entry.objects.filter(author=author).order_by("-published")
    followers_info = author.followers_info or {}
    followers = Author.objects.filter(id__in=list(followers_info.keys())) if followers_info else []
    following = author.following.all()
    follow_requests = Follow.objects.filter(object=author.id, state="REQUESTED")
    friends_data = author.friends or {}
    friends = Author.objects.filter(id__in=list(friends_data.keys())) if friends_data else []

    context = {
        "author": author,
        "entries": entries,
        "followers": followers,
        "following": following,
        "follow_requests": follow_requests,
        "friends": friends,
        "form": form,
    }

    return render(request, "profile.html", context)

FOLLOW_STATE_CHOICES = ["REQUESTED", "ACCEPTED", "REJECTED"]


@login_required
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
    })


@login_required
def followers(request):
    actor = Author.from_user(request.user)

    # Handle POST remove follower
    if request.method == "POST":
        follower_id = request.POST.get('author_id')
        follower = get_object_or_404(Author, id=follower_id)

        # Remove from followers_info and following
        actor.followers_info.pop(follower.id, None)
        actor.save()

        follower.following.remove(actor)
        follower.save()

        # Delete Follow object if exists
        Follow.objects.filter(actor=follower, object=actor.id).delete()

        # Update friends
        actor.update_friends()
        follower.update_friends()

        return redirect(request.META.get('HTTP_REFERER', 'followers'))

    # GET request: show followers
    followers_ids = actor.followers_info.keys()
    authors = Author.objects.filter(id__in=followers_ids)

    query = request.GET.get('q', '')
    if query:
        authors = authors.filter(username__icontains=query)

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

        if hasattr(target_author, "followers_info") and isinstance(target_author.followers_info, dict):
            # Convert the actor’s ID (FQID) to string key if needed
            actor_id_str = str(actor.id)

            if actor_id_str in target_author.followers_info:
                del target_author.followers_info[actor_id_str]
                target_author.save(update_fields=["followers_info"])

        # Update friends
        actor.update_friends()
        target_author.update_friends()

        return redirect(request.META.get('HTTP_REFERER', 'following'))

    # GET request: show following
    authors = actor.following.all()

    query = request.GET.get('q', '')
    if query:
        authors = authors.filter(username__icontains=query)

    return render(request, "search.html", {
        "authors": authors,
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
            # Update ManyToMany
            follower_author = follow_request.actor
            actor.followers_info[follower_author.id] = follower_author.username
            actor.save()
            follower_author.following.add(actor)
            follower_author.save()

            # Update friends
            actor.update_friends()
            follower_author.update_friends()
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
    friends_ids = actor.friends.keys()
    authors = Author.objects.filter(id__in=friends_ids)

    # Optional: filter by search query
    query = request.GET.get('q', '')
    if query:
        authors = authors.filter(username__icontains=query)

    return render(request, "search.html", {
        "authors": authors,
        "query": query,
        "page_type": "friends",  # Used in template to hide buttons
    })

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
    

''' 
view displays the entry as well as comments below it
'''
#! WIP
@login_required
def entry_detail(request, entry_uuid):
    try:
        entry = Entry.objects.get(id=entry_uuid)
    except Entry.DoesNotExist:
        entry = get_object_or_404(Entry, id__endswith=str(entry_uuid))
    
    viewer = Author.from_user(request.user)
        # Enforce visibility (deny if FRIENDS-only and viewer isn't allowed)
    if entry.visibility == "FRIENDS":
        # entry.author.friends is a dict of FQID -> info (per your model)
        allowed_fqids = set(entry.author.friends.keys()) if entry.author.friends else set()
        # allow the author themself too
        allowed_fqids.add(str(entry.author.id))
        if not viewer or str(viewer.id) not in allowed_fqids:
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
    else:
        return Response({"error": "Unsupported type"}, status=400)
    
def handle_create(data, author):
    
    return
def handle_like(data,author):
    return
def handle_comment(data,author):
    return
def handle_follow(data,author):
    return


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
    entries = Entry.objects.all().order_by('-is_posted')
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

        entry.delete()
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
        context['entries'] = Entry.objects.select_related("author").all()
        context['comment_form'] = CommentForm()
        
        return render(request, "new_post.html", context | {'entries': entries})

    # FEATURE EDIT BUTTON CLICKED 
    if request.method == "POST" and "entry_edit" in request.POST:
        primary_key = request.POST.get('entry_edit')
        editing_entry = get_object_or_404(Entry, id=primary_key)

        form = EntryList(instance=editing_entry)
        context["editing_entry"] = editing_entry
        context["form"] = form
        context["entries"] = Entry.objects.select_related("author").all()
        return render(request, "new_post.html", context | {'entries': entries})

    context['form'] = form 
    context["editing_entry"] = editing_entry
    # context["entries"] = Entry.objects.select_related("author").all()
 

    return render(request, "new_post.html", context | {'entries': entries})