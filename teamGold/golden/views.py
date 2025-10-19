from django.shortcuts import render, redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.urls import reverse

# Import login authentication stuff
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
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
    # we want to log users out when they want to sign up
    logout(request)

    if request.method == "POST":
        # create a form instance and populate it with data from the request
        form = CustomUserForm(request.POST)
        
        # we don't want to create a user if the inputs are not valid since that can raise errors
        if form.is_valid():
            user = form.save()
            print(user)
            login(request, user)

            return redirect("/golden/")
            # return HttpResponseRedirect(reverse("index"))
    else:
        form = CustomUserForm()

    return render(request, "signup.html", {"form": form})


# This code is coming from a conflict, saved just in case
# def profile_view(request):
#     return render(request, 'profile.html')
