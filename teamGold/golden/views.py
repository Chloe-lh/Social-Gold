from django.shortcuts import render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.urls import reverse

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.views.generic.edit import FormView
from .forms import CustomUserForm

from .models import Author


# login_required brings the user to the login page if they are not logged in
@login_required
def index(request):
    objects = Author.objects.all()
    print("USERS:")
    for obj in objects:
        print(obj.username)
    return render(request, "index.html")

def signup(request):
    if request.method == "POST":
        # create a form instance and populate it with data from the request:
        form = CustomUserForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            user = form.save()
            print(user)
            login(request, user)
            
            # Get ?next= URL if present, otherwise go to /golden/
            next_url = request.POST.get("next") or request.GET.get("next") or "/golden/profile/"    # TODO: Change the link to homepage after it's done
            return redirect(next_url)

    else:
        form = CustomUserForm()

    # Pass along any ?next= parameter to the signup form
    next_url = request.GET.get("next", "")
    return render(request, "signup.html", {"form": form, "next": next_url})


@login_required
def profile_view(request):
    return render(request, 'profile.html')
  
# class signup(FormView):
#     template_name = "signup.html"
#     form_class = CustomUserForm
#     success_url = "/"

#     def form_valid(self, form):
#         user = form.save()
#         login(self.request, user)
#         return super().form_valid(form)

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