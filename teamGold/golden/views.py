from django.shortcuts import render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.urls import reverse
from django.conf import settings

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.views.generic.edit import FormView
from .forms import CustomUserForm
import uuid
import markdown

from .models import Author, Entry
from django.contrib.auth import get_user_model


# login_required brings the user to the login page if they are not logged in
@login_required
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

            return redirect('profile')           # TODO: Change the link to homepage after it's done
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

    for entry in entries:
        if entry.contentType == "text/markdown":
            entry.rendered_content = markdown.markdown(entry.content)
        else:
            entry.rendered_content = entry.content

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