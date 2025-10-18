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
            login(self.request, user)
            
            return HttpResponseRedirect(reverse("index"))

    else:
        form = CustomUserForm()
    return render(request, "signup.html", {"form": form})

# class signup(FormView):
#     template_name = "signup.html"
#     form_class = CustomUserForm
#     success_url = "/"

#     def form_valid(self, form):
#         user = form.save()
#         login(self.request, user)
#         return super().form_valid(form)