from django.shortcuts import render
from rest_framework import generics
from .models import Node
from .serializers import NodeSerializer

# # Create your views here.
def index(request):
    return render(request, "index.html")

def base(request):
    return render(request, "base.html")

def profile_view(request):
    return render(request, 'profile.html')

def login_view(request):
    # a post is sent when the log in button is pressed
    if request.method == "POST":
    # get credentials from request
        user = request.get("userName")
        password = request.get("password")
        # also need password authentication
        try: 
            author = Author.objects.get(userName=user)
            if not author.is_admin and author.is_approved:
                return render(request, "login.html", "error: User has not been approved")
            if author.password == password:
                # log in 
                return redirect("home")
        except Author.DoesNotExist:
            return render(request, "login.html", "error: User does not exist")
    # User authentication and user is approved -> show home page?
    return render(request, "login.html")
                
'''
parameter: id from the URL to find specific node
called when a client (node) makes a GET request to the Node id 
Uses NodeSerializer to serialize and display the fields in the Node model
'''
class NodeDetailAPIView(generics.RetrieveAPIView):
    queryset = Node.objects.all()
    serializer_class = NodeSerializer
    lookup_field = 'id'