# REST FRAMEWORK IMPORTS 
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# DJANGO IMPORTS
from django.core.paginator import Paginator

# LOCAL IMPORTS
from golden.models import Author
from golden.serializers import AuthorSerializer
from golden.services import paginate

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class AuthorsListView(APIView):
    """
    API view to list all authors (for remote node discovery).
    - GET /api/authors/ returns a list of all authors
    - Supports pagination via query parameters: ?page=<number>&size=<number>
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get a list of all authors on this node",
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number", type=openapi.TYPE_INTEGER),
            openapi.Parameter('size', openapi.IN_QUERY, description="Page size", type=openapi.TYPE_INTEGER),
        ],
        responses={
            200: openapi.Response(
                description="List of authors",
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
            401: "Unauthorized"
        }
    )
    def get(self, request):
        # Get all authors
        authors = Author.objects.all().order_by('username')
        
        # Handle pagination
        page = request.GET.get('page', 1)
        size = request.GET.get('size', 50)
        
        try:
            page = int(page)
            size = int(size)
        except (ValueError, TypeError):
            page = 1
            size = 50
        
        # Paginate
        paginator = Paginator(authors, size)
        page_obj = paginator.get_page(page)
        
        # Serialize
        serializer = AuthorSerializer(page_obj.object_list, many=True)
        
        # Return in paginated format (matching ActivityPub style)
        return Response({
            "type": "authors",
            "items": serializer.data,
            "page": page,
            "size": size,
            "total": paginator.count
        }, status=status.HTTP_200_OK)

