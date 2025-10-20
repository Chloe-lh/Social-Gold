# BASE DJANGO 
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden

# REST FRAMEWORKS 
from rest_framework.decorators import api_view
from rest_framework.response import Response

# BASE GOLDEN
from golden.models import Entry, EntryImage, Author
from golden.entry import EntryList
from .forms import CustomUserForm

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.generic.edit import FormView
import uuid

from .models import Author, Entry

# Imports for entries
from django.contrib.auth import get_user_model
from .decorators import require_author
import markdown 

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
    user = request.user
    try:
        author = Author.objects.get(id=user.id)
    except Author.DoesNotExist:
        author = None

    entries = Entry.objects.filter(author=author).order_by('published')

    followers_count = author.followers_set.count() if author else 0
    following_count = author.following.count() if author else 0

    context = {
        'author': author,
        'entries': entries,
        'followers_count': followers_count,
        'following_count': following_count,
    }
    return render(request, 'profile.html', context)

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