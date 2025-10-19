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
        next_page = request.POST['next']
        
        # we don't want to create a user if the inputs are not valid since that can raise errors
        if form.is_valid():
            user = form.save()
            login(request, user)
            if not next_page:
                next_page = "/golden/"

            return redirect(next_page)
    else:
        # just in case the method is not GET
        try:
            next_page = request.GET.get('next')
            print(next_page)
        except Exception as e:
            next_page = None
        
        form = CustomUserForm()

    if next_page is not None:
        return render(request, "signup.html", {"form": form, "next": next_page})
    else:
        return render(request, "signup.html", {"form": form})


# This code is coming from a conflict, saved just in case
# def profile_view(request):
#     return render(request, 'profile.html')
