import uuid
from django.conf import settings
from urllib.parse import unquote, urlparse
from rest_framework.response import Response
from .models import Node
import requests
import json
from django.db import transaction
from .models import Author
import logging
from django.core.paginator import Paginator
'''
helper function for remote nodes
sends a POST request with with HTTP Authentication
ei  When a local author follows a remote author
    When a local author likes or comments on a remote post
'''
def send_to_remote_node(node, url, data):
    response = requests.post(
        url,
        json=data,
        auth=(node.auth_user, node.auth_pass)
    )
    return response

def get_remote_author_profile(remote_node_url, author_id):
    url = f"{remote_node_url}/api/profile/{author_id}/"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None


def resolve_or_create_author(author_input, create_if_missing=False):
    """
    Resolve an incoming author reference to a local `Author` instance.

    - `author_input` may be:
        - an `Author` instance -> returned as-is
        - a string FQID (e.g. "http://node.com/api/authors/<uuid>/")
        - a dict containing at least an 'id' key
    - If `create_if_missing` is True and the author is remote and the
      author host matches a known `Node`, this will fetch the remote
      profile (best-effort) and create a minimal, unprivileged placeholder
      Author (is_active=False, is_approved=False).

    Errors:
      - Author.DoesNotExist if the author is not found and creation is
        not allowed.
      - requests.RequestException when remote fetch fails.
    """
    # If caller passed a model instance, return it
    if hasattr(author_input, '__class__') and getattr(author_input, 'pk', None):
        return author_input

    # Normalize to an id string
    if isinstance(author_input, dict):
        author_id = author_input.get('id')
    else:
        author_id = author_input

    if not author_id:
        raise Author.DoesNotExist("Author id missing")

    # Try local lookup first
    try:
        return Author.objects.get(pk=author_id)
    except Author.DoesNotExist:
        if not create_if_missing:
            raise

    # At this point author must be remote
    parsed = urlparse(author_id)
    host_base = f"{parsed.scheme}://{parsed.netloc}"

    # Ensure the host belongs to a known/trusted Node
    node = Node.objects.filter(id__startswith=host_base).first()
    if not node:
        raise PermissionError(f"Author host {host_base} is not a known node")

    # Try to fetch profile from remote node 
    author_uuid = author_id.rstrip('/').split('/')[-1]
    try:
        profile = get_remote_author_profile(node.id.rstrip('/'), author_uuid)
    except Exception as e:
        logging.exception("Failed to fetch remote author profile")
        raise

    if not profile or profile.get('id') != author_id:
        # If remote profile missing or mismatched, do not create
        raise Author.DoesNotExist("Remote author profile mismatch or not found")

    # Create a minimal placeholder Author to be nested
    with transaction.atomic():
        # Avoid duplicate creation in race conditions
        author, created = Author.objects.get_or_create(
            id=profile['id'],
            defaults={
                'username': f"remote_{uuid.uuid4().hex[:8]}",
                'name': profile.get('displayName') or profile.get('name') or '',
                'host': host_base,
                'is_active': False,
                'is_approved': False,
            }
        )
    return author
'''
Extracts remote node object from fqid (https://node1.com/api/authors/<uuid>/)
    will return node instance or None if host is local or not trusted
'''
def get_remote_node_from_fqid(fqid):
    
    if not fqid: return None
    fqid = unquote(str(fqid)).rstrip('/')
    try:
        parsed = urlparse(fqid)
        if not parsed.scheme or not parsed.netloc:
            return None
        remote_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    except Exception:
        return None
    if settings.LOCAL_NODE_URL == remote_base:
        return None

    node = Node.objects.filter(id__startswith=remote_base).first()
    if not node:
        return None
    if not node.is_active:
        return None
    return node

'''
create fqid (id) for comment
author.id is a already createdd fqid, so append to the end
'''
def generate_comment_fqid(author, entry):
    comment_uuid = uuid.uuid4()
    return f"{author.id}/commented/{comment_uuid}"
'''
convert from fqid to uuid
'''
def fqid_to_uuid(fqid):
    unquoted_fqid = unquote(fqid)
    uid = unquoted_fqid.strip("/").split("/")[-1]
    return uid
'''
pagination for listing comments and likes
    params: allowed - filtered list of items 
    returns: page object that is input for the correct serializer
    (CommentSerializer(page_obj.object_list, many=True).data)
'''
def paginate(request, allowed):
    try:
        page_size = int(request.query_params.get('size', 10))
    except Exception:
        page_size = 10
    try:
        page_number = int(request.query_params.get('page', 1))
    except Exception:
        page_number = 1

    paginator = Paginator(allowed, page_size)
    page_obj = paginator.get_page(page_number)
    return page_obj


# def generate_comment_like_fqid(author, comment):
#     comment_uuid = uuid.uuid4()
#     return f"{settings.LOCAL_NODE_URL}/api/authors/{author.uid}/commented/{comment_uuid}"

# def generate_entry_like_fqid(author, entry):
#     like_uuid = uuid.uuid4()
#     return f"{settings.LOCAL_NODE_URL}/api/authors/{author.uid}"



def get_host_node(url):
    host_node = Node.objects.get(host=url)
    if not host_node.is_active:
        return Response(f"Node for host {url} is not active", status=status.HTTP_404_BAD_REQUEST)
    
    return host_node

'''
checks if a node is remote by checking if its URL (id) is different from 
local nodes URL
'''
def is_remote_node(node):
    return node.id != settings.LOCAL_NODE_URL
