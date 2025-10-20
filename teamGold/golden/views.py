# BASE DJANGO 
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden
from django.contrib.auth.backends import ModelBackend

# REST FRAMEWORKS 
from rest_framework.decorators import api_view
from rest_framework.response import Response

# BASE GOLDEN
from golden.models import Entry, EntryImage, Author, Follow
from golden.entry import EntryList
from .forms import CustomUserForm, ProfileForm

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.generic.edit import FormView
from django.utils import timezone
from django.contrib.auth.views import LoginView
import uuid

from .models import Author, Entry

# Imports for entries
from django.contrib.auth import get_user_model
from .decorators import require_author


@login_required
def index(request):
    objects = Author.objects.values()
    print("USERS:")
    for obj in objects:
        print(obj['username']) 
    return render(request, "index.html")
from django.shortcuts import render
from rest_framework import generics
from .models import Node
from .serializers import NodeSerializer

# # Create your views here.
def index(request):
    return render(request, "index.html")

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

            return redirect('home')     
    else:
        form = CustomUserForm()
        # next_page = request.GET.get('next')

    return render(request, "signup.html", {"form": form})

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
    user = request.user
    try:
        author = Author.objects.get(id=user.id)
    except Author.DoesNotExist:
        author = None

    entries = Entry.objects.filter(author=author).order_by('published')

    followers_count = author.followers_set.count() if author else 0
    following_count = author.following.count() if author else 0

    if request.method == 'POST' and 'edit_profile' in request.POST:
        form = ProfileForm(request.POST, request.FILES, instance=author)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = ProfileForm(instance=author)

    context = {
        'author': author,
        'entries': entries,
        'followers_count': followers_count,
        'following_count': following_count,
        'form': form,
    }
    return render(request, 'profile.html', context)

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
            actor.save(update_fields=["following"])

        if hasattr(target_author, "followers_info") and isinstance(target_author.followers_info, dict):
            # Convert the actor’s ID (FQID) to string key if needed
            actor_id_str = str(actor.id)

            if actor_id_str in target_author.followers_info:
                del target_author.followers_info[actor_id_str]
                target_author.save(update_fields=["followers_info"])

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
@require_author 
def home(request):
    """
    @require_author is linked with deorators.py to ensure user distinction
    """
    if request.current_author is None:
        return redirect('signup')
    
    context = {}
    form = EntryList()
    editing_entry = None # because by default, users are not in editing mode 
    entries = Entry.objects.all().order_by('-is_posted')
    context['entries'] = entries

    # FEATURE POST AN ENTRY
    if request.method == "POST" and "entry_post" in request.POST:
        entry_id = f"https://node1.com/api/entries/{uuid.uuid4()}"

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
                    
        return redirect('home')
    
    # FEATURE DELETE AN ENTRY 
    if request.method == "POST" and "entry_delete" in request.POST:
        primary_key = request.POST.get('entry_delete')
        entry = Entry.objects.get(id=primary_key)

        # also for testing purposes 
        if entry.author.id != request.current_author.id:
            return HttpResponseForbidden("This isn't yours")

        entry.delete()
        return redirect('home')
    
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
        return render(request, "home.html", context | {'entries': entries})

    # FEATURE EDIT BUTTON CLICKED 
    if request.method == "POST" and "entry_edit" in request.POST:
        primary_key = request.POST.get('entry_edit')
        editing_entry = get_object_or_404(Entry, id=primary_key)

        form = EntryList(instance=editing_entry)
        context["editing_entry"] = editing_entry
        context["form"] = form
        context["entries"] = Entry.objects.select_related("author").all()
        return render(request, "home.html", context | {'entries': entries})

    context['form'] = form 
    context["editing_entry"] = editing_entry
    context["entries"] = Entry.objects.select_related("author").all()

    return render(request, "home.html", context | {'entries': entries})

