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

def notify(author, data):
    """
    Notify followers of `author` by POSTing `data` to each follower's node inbox.

    - `author` is an `Author` instance (the user whose followers should be notified)
    - `data` is a JSON-serializable payload to send (e.g. the comment/like/entry/activity object)

    - For each follower, derive the follower's host and look up a matching `Node`.
    - If a matching `Node` exists and is active, POST `data` to that node's `/inbox` URL
      using any HTTP auth configured on the `Node`.
    """
    logger = logging.getLogger(__name__)
    results = []

    # Use the reverse relation 'followers_set' to get Authors who follow `author`.
    try:
        followers_qs = author.followers_set.all()
    except Exception:
        logger.exception("Failed to get followers for author %s", getattr(author, 'id', None))
        return results

    for follower in followers_qs:
        try:
            # follower.id is an author's FQID, e.g. 'http://nodebbbb/api/authors/222/'
            parsed = urlparse(str(follower.id))
            if not parsed.scheme or not parsed.netloc:
                logger.debug("Skipping follower with invalid id: %s", follower.id)
                continue

            follower_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')

            # Look up a Node whose id starts with the follower's host
            node = Node.objects.filter(id__startswith=follower_base).first()
            if not node:
                logger.debug("No Node found for follower host %s (follower=%s)", follower_base, follower.id)
                continue
            if not getattr(node, 'is_active', False):
                logger.debug("Skipping inactive node %s for follower %s", node.id, follower.id)
                continue

            inbox_url = node.id.rstrip('/') + '/inbox'
            auth = None
            if getattr(node, 'auth_user', None):
                auth = (node.auth_user, node.auth_pass)

            logger.debug("Posting notification to follower %s inbox %s", follower.id, inbox_url)
            resp = requests.post(
                inbox_url,
                json=data,
                auth=auth,
                headers={'Content-Type': 'application/json'},
                timeout=5,
            )
            results.append((follower.id, resp.status_code))
            if not (200 <= resp.status_code < 300):
                logger.warning("Failed to notify follower %s at %s: %s", follower.id, inbox_url, resp.status_code)

        except Exception as e:
            logger.exception("Exception while notifying follower %s: %s", getattr(follower, 'id', None), e)
            results.append((getattr(follower, 'id', None), None))

    return results


def get_remote_author_profile(remote_node_url, author_id):
    url = f"{remote_node_url}/api/profile/{author_id}/"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

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
def generate_comment_fqid(author):
    comment_uuid = uuid.uuid4()
    return f"{author.id}/commented/{comment_uuid}"

def generate_like_fqid(author):
    like_uuid = uuid.uuid4()
    return f"{author.id}/liked/{like_uuid}"

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
