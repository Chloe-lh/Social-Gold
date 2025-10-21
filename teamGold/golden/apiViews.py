from rest_framework import generics
from .models import Author, Entry, Node
from .serializers import AuthorSerializer, EntrySerializer, NodeSerializer
'''
This contains Django REST Framework class views for API endpoints
 - it handles requests from remote nodes and returns JSON data
 - the client will then parse and display the JSON data so
   the user can view the side

   some info:

   - class based API views 
        - complex endpoints
        - ei sending profile data
   - function based API views
        - minimal logic
        - ei sending a notification
'''

'''
Django REST Framework view that returns authors profiles data
as JSON data for other API nodes
when a remote node wants to display an authors profile from our local node
    - remote node sends a GET request to our API endpoint (http:://golden.node.com/api/profile/<id>)
    - our node handles the request and serializers authors data to JSON
'''
class GETProfileAPIView(generics.RetrieveAPIView):
    queryset = Author.objects.all() #get all authors from database
    serializer_class = AuthorSerializer #get serializer type
    lookup_field = 'id' # look up author in database with id
    # DRF will automatically find object, serialize, and send response
    # can edit swagger schema here

class GETEntryAPIView(generics.RetrieveAPIView):
    queryset = Entry.objects.all()
    serializer_class = EntrySerializer
    lookup_field = 'id'

class GETNodeAPIView(generics.RetrieveAPIView):
    queryset = Node.objects.all()
    serializer_class = NodeSerializer
    lookup_field = 'id'

