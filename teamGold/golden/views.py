from django.shortcuts import render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.urls import reverse
from django.conf import settings

# Import login authentication stuff (# get_user_model added from entries)
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.views.generic.edit import FormView
from .forms import CustomUserForm
import uuid

# Imports for entries
from golden.models import Entry, Author
from golden.entry import EntryList
import markdown 

# Create your views here.
def index(request):
    objects = Author.objects.values()
    print("USERS:")
    for obj in objects:
        print(obj.username) # type: ignore
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

            return redirect('profile')           # TODO: Change the link to homepage after it's done
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
def home(request):
    context = {}
    form = Entry()
    entries = Entry.objects.all()
    context['entries'] = entries
    context['title'] = "Home"

    # User clicked the Post Button
    if request.method == "POST" and "entry_post" in request.POST:
        entry_id = "https://node1.com/api/entries/" + str(uuid.uuid4()), 

        # This is temporary because login feature doesn't exist yet
        if request.user.is_authenticated:
            try: 
                author = Author.objects.get(userName=request.user.username) 
            except:
                author = Author.objects.create(userName=request.user.username, password=request.user.password)

        markdown_content = request.POST['content']
        html_content = markdown.markdown(markdown_content)
        entry = Entry(
            id=entry_id,
            author=author, # type: ignore
            content=html_content,
            visibility=request.POST.get('visibility', 'PUBLIC')
        )
        entry.save()

        return redirect('home')
    
    # User clicks delete button
    if request.method == "POST" and "entry_delete" in request.POST:
        primary_key = request.POST.get('entry_delete')
        entry = Entry.objects.get(id=primary_key)
        entry.delete()
        return redirect('home')

    # User clicks the edit button
    if request.method == "POST" and "entry_edit" in request.POST:
        primary_key = request.POST.get('entry_edit')
        entry = Entry.objects.get(id=primary_key)
        form = EntryList(request.POST, instance=entry)
        entry.save()
    context['form'] = form 
    return render(request, "home.html", context)