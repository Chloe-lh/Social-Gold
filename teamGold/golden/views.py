# BASE DJANGO 
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden
from django.db.models import Q

# REST FRAMEWORKS 
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

# BASE GOLDEN
from golden import models
from golden.models import Entry, EntryImage, Author, Comments, Like, Follow
from golden.entry import EntryList
from .forms import CustomUserForm

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.generic.edit import FormView
import uuid
# view decorator
from django.views.decorators.http import require_POST

# Imports for entries
from django.contrib.auth import get_user_model
from .decorators import require_author
import markdown 

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from django.utils import timezone


from golden.serializers import InboxSerializer


def index(request):
    objects = Author.objects.values()
    print("USERS:")
    for obj in objects:
        print(obj['username']) 
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

@login_required
def profile_view(request):
    return render(request, 'profile.html')

@login_required
def search_authors(request):
    query = request.GET.get('q', '')  # get search term from input
    if query:
        authors = Author.objects.filter(username__icontains=query)
    else:
        authors = Author.objects.all()  # display all if no search
    return render(request, "search.html", {"authors": authors, "query": query, 'page_type': 'search_authors',})

@login_required
def followers(request):
    query = request.GET.get('q', '')  # get search term from input
    if query:
        authors = Author.objects.filter(username__icontains=query)
    else:
        authors = Author.objects.all()  # display all if no search
    return render(request, "search.html", {"authors": authors, "query": query, 'page_type': 'followers',})

@login_required
def following(request):
    query = request.GET.get('q', '')  # get search term from input
    if query:
        authors = Author.objects.filter(username__icontains=query)
    else:
        authors = Author.objects.all()  # display all if no search
    return render(request, "search.html", {"authors": authors, "query": query, 'page_type': 'following',})

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



@login_required
def stream_view(request):
    # 1️⃣ Get the Author object for the logged-in user
    user_author = Author.objects.get(user=request.user)

    # 2️⃣ Get all accepted follows (authors this user follows)
    follows = Follow.objects.filter(actor=user_author, state='ACCEPTED')
    followed_author_fqids = [f.object for f in follows]

    # 3️⃣ Determine authors who are "friends" (mutual follows)
    friends_fqids = []
    for f in follows:
        try:
            # Check if the followed author also follows the user
            reciprocal = Follow.objects.get(actor__id=f.object, object=user_author.id, state='ACCEPTED')
            friends_fqids.append(f.object)
        except Follow.DoesNotExist:
            continue

    # 4️⃣ Query entries according to visibility rules

    entries = Entry.objects.filter(
        deleted=False
    ).filter(
        Q(visibility='PUBLIC') |  # Public entries: everyone can see
        Q(visibility='UNLISTED', author__id__in=followed_author_fqids) |  # Unlisted: only followers
        Q(visibility='FRIENDS', author__id__in=friends_fqids)  # Friends-only: only friends
    ).order_by('-is_updated', '-published')  # Most recent first

    # 5️⃣ Prepare context for the template
    context = {
        'entries': entries,
        'user_author': user_author,
        'followed_author_fqids': followed_author_fqids,
        'friends_fqids': friends_fqids
    }

    # 6️⃣ Render the stream page extending base.html
    return render(request, 'stream.html', context)

class InboxView(APIView):
    def post(self, request, author_id):
        try:
            recipient = Author.objects.get(id=author_id)
        except Author.DoesNotExist:
            return Response({"error": "Author not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = InboxSerializer(data=request.data)
        if serializer.is_valid():
            created_obj = serializer.save()  # creates Follow/Like/Comment/Post

            return Response({"message": f"Delivered to {recipient.display_name}'s inbox"},
                            status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)