import uuid
from django.conf import settings
import requests
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

'''
create fqid (id) for comment
author.id is a already createdd fqid, so append to the end
'''
def generate_comment_fqid(author, entry):
    comment_uuid = uuid.uuid4()
    return f"{author.id}/commented/{comment_uuid}"

# def generate_comment_like_fqid(author, comment):
#     comment_uuid = uuid.uuid4()
#     return f"{settings.LOCAL_NODE_URL}/api/authors/{author.uid}/commented/{comment_uuid}"

# def generate_entry_like_fqid(author, entry):
#     like_uuid = uuid.uuid4()
#     return f"{settings.LOCAL_NODE_URL}/api/authors/{author.uid}"

'''
checks if a node is remote by checking if its URL (id) is different from 
local nodes URL
'''
def is_remote_node(node):
    return node.id != settings.LOCAL_NODE_URL
