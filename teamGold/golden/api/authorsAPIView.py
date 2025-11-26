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
        except (ValueError, TypeError):
            page = 1
        
        try:
            size = int(size)
        except (ValueError, TypeError):
            size = 50
        
        # Paginate
        #page_obj = paginate(request, authors, 50)
        page_obj = paginate(request, authors)

        # Serialize
        serializer = AuthorSerializer(page_obj.object_list, many=True)
        
        return Response({
            "type": "authors",
            "authors": serializer.data,  # Changed from "items" to "authors" to match spec
            #"page": page,
            "page": page_obj.number,
            #"size": size,
            "size": page_obj.paginator.per_page,
            #"total": paginator.count
            "total": page_obj.paginator.count,
        }, status=status.HTTP_200_OK)


class SingleAuthorAPIView(APIView):
    """
    API view to get a single author by UUID.
    - GET /api/authors/<author_uuid>/ returns details of a specific author
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]


    @swagger_auto_schema(
        operation_summary="Get a single author",
        operation_description="Returns details of a specific author given their UUID or full FQID.",
        responses={
            200: openapi.Response(description="Author found"),
            404: openapi.Response(description="Author not found"),
        }
    )
    def get(self, request, author_uuid):
        from golden.services import fqid_to_uuid, is_local
        from django.conf import settings
        
        # Try to find author by UUID - construct FQID if needed
        author = None
        
        # First try: if it's a UUID, construct full FQID
        if '-' in author_uuid and '/' not in author_uuid:
            local_fqid = f"{settings.SITE_URL.rstrip('/')}/api/authors/{author_uuid}"
            author = Author.objects.filter(id=local_fqid).first()
        
        # Second try: if it's a full FQID
        if not author:
            author = Author.objects.filter(id=author_uuid).first()
        
        # Third try: try with trailing slash
        if not author:
            author = Author.objects.filter(id=f"{author_uuid}/").first()
        
        # Fourth try: extract UUID from FQID and match
        if not author and '/api/authors/' in author_uuid:
            uuid_part = author_uuid.split('/api/authors/')[-1].rstrip('/')
            local_fqid = f"{settings.SITE_URL.rstrip('/')}/api/authors/{uuid_part}"
            author = Author.objects.filter(id=local_fqid).first()
        
        if not author:
            return Response({'detail': 'Author not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = AuthorSerializer(author)
        return Response(serializer.data, status=status.HTTP_200_OK)

