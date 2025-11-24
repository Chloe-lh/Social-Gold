# REST FRAMEWORK IMPORTS 
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# DJANGO IMPORTS
from django.shortcuts import get_object_or_404

# LOCAL IMPORTS
from golden.models import Author
from golden.serializers import AuthorSerializer

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class FollowersView(APIView):
    """
    API view to determine if an remote author is following the local author.
    - GET /api/authors/<path:author_serial>/followers/<path:foreign_author_fqid> returns the remote author if they are following the current author, 404 otherwise
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Checks if a remote author is currently following the local author",
        responses={
            200: openapi.Response(
                description="Author information",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'type': openapi.Schema(type=openapi.TYPE_STRING, example='authors'),
                        'items': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        )
                    }
                )
            ),
            404: openapi.Response(description="Author is not a follower")
        }
    )
    def get(self, request):
        pass
        # TODO: waiting on node to node follower/following
        # returns remote author information if they are following the local author
        # return 404 otherwise

        # send a get author request to the node and return the response?

        # authors = Author.objects.all().order_by('username')
        
        # # Pagination
        # page = request.GET.get('page', 1)
        # size = request.GET.get('size', 50)

        # page_obj = paginate(request, authors, 50)
        
        # # Serialize
        # serializer = AuthorSerializer(page_obj.object_list, many=True)
        
        # # Return in paginated format (matching ActivityPub style)
        # return Response({
        #     "type": "authors",
        #     "items": serializer.data,
        #     "page": page,
        #     "size": size,
        #     "total": page_obj.object_list.count()
        # }, status=status.HTTP_200_OK)