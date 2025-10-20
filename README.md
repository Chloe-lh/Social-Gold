[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/etkNZkSE)
CMPUT404-project-socialdistribution
===================================

CMPUT404-project-socialdistribution

See [the web page](https://uofa-cmput404.github.io/general/project.html) for a description of the project.

Make a distributed social network!

**Team Members:**
- Aesoji
- chobo
- Emoji_King
- Irisveil
- Pooja
- zaara

## License

* Choose an OSI approved license, name it here, and copy the license text to a file called `LICENSE`.

## Copyright

The authors claiming copyright, if they wish to be known, can list their names here...

---

# Overview

The Golden API provides RESTful endpoints for managing authors, entries, comments, likes, follows, nodes, and entry images.
All endpoints support HTTP Basic Authentication to ensure secure access.

## Base API Information
| Hostname | localhost |
| Port | 8000 |
| Prefix | /api |
| Auth Type | HTTP Basic Auth |

**Authentication Credentials:**
- Username: admin
- Password: admin_password

"""
Django REST Framework API

These endpoints are consumed by remote nodes and local clients. Views return
JSON only. Class-based APIViews are used for resources with model-backed
lookups. Function-based views may be used for simple, stateless actions
such as lightweight notifications.

Authentication
- HTTP Basic Auth is required for all endpoints in this module.
- Include credentials in the Authorization header:
  Authorization: Basic <base64(username:password)>

HTTP and Content Negotiation
- Requests and responses use application/json unless otherwise specified.
- Successful responses contain a JSON body. Not Found returns 404 with no body.

Routing summary (current)
- GET /api/Profile/<id>/       -> Author by FQID (URL primary key)
- GET /api/Entry/<id>/         -> Entry by FQID
- GET /api/Node/<id>/          -> Node by FQID (Node.id is a URL)
- GET /api/Follow/<id>/        -> Follow activity by FQID
- GET /api/Like/<id>/          -> Like activity by FQID
- GET /api/Comment/<id>/       -> Comment by FQID
- GET /api/EntryImage/<id>/    -> EntryImage by numeric id

Notes on identifiers
- Most models use a fully qualified URL as the primary key (FQID). Example:
  https://node1.com/api/entries/9b3a2e4b-1f1d-4a0a-a7fe-33c2b1a4c124
- EntryImage uses the default integer primary key.

Typical flow for a remote node reading a local author profile
1) Remote node issues GET to:
   http://<your-host>/api/Profile/<author-fqid> 
2) This service retrieves the Author by primary key and serializes it with AuthorSerializer.
3) The JSON response is returned with 200 OK.

Example request (curl)
  curl -i \
    -H "Accept: application/json" \
    -u apiuser:pass \
    "http://localhost:8000/api/Profile/https://node1.com/api/authors/9d7e.../"

Example success response (200)
{
  "id": "https://node1.com/api/authors/9d7e...",
  "type": "author",
  "username": "alice",
  "host": "https://node1.com/",
  "github": "",
  "web": "",
  "profileImage": "https://...",
  "is_approved": true,
  "date_joined": "2025-10-19T23:45:12Z",
  "followers_info": {},
  ...
}

Example not found (404)
  No body

Authentication examples
- Without credentials:
  GET /api/Entry/<id> -> 401 Unauthorized
  Response header includes: WWW-Authenticate: Basic realm="api"
- With valid credentials:
  GET /api/Entry/<id> -> 200 OK with JSON body

Status codes used
- 200 OK      Resource found and returned as JSON
- 401 Unauthorized  Missing or invalid Basic Auth
- 404 Not Found     Resource does not exist
- 415 Unsupported Media Type  Only if a client submits a non-JSON body to a JSON-only endpoint

Schema stability
- Serializers define the response shape. Required keys should remain stable.
- Additional keys may be added as long as existing clients are not broken.

Spec compatibility note
- Course examples often use nested routes like:
  /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_ID}
- This service provides capitalized, FQID-based detail endpoints as listed above.
- If needed for compatibility, add alias routes that resolve to the same views and document both forms.

Function-based view example (minimal notification)

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

@api_view(["POST"])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def notify(request):
    # Minimal logic: validate payload and enqueue or log a notification
    payload = request.data or {}
    if "message" not in payload:
        return Response({"message": "Missing 'message' field"}, status=status.HTTP_400_BAD_REQUEST)
    # ... perform side effect here ...
    return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)

URL pattern example:
  path("api/notify/", notify, name="notify")

Testing guidance
- For each GET endpoint, test 200 with a real FQID and 404 with a fake FQID.
- For auth, assert 401 without Authorization and 200 with valid Basic credentials.
- For function views like /api/notify/, test 202 on valid input and 400 on invalid input.
"""




Short answer: Yes—for your current API surface.

You only expose GET detail endpoints in apiViews.py. There are no write APIs (no POST/PATCH/DELETE) for stories like “create entry,” “like,” “comment,” or “follow.”
→ Your tests create via Django models and then verify via API GET, which matches the rule for stories without an API. ✅

Where there is API functionality (GET reads + BasicAuth), you test it through the API:

Success (200) and Not Found (404) for each endpoint. ✅

Auth behavior (BasicAuthBehaviorTests): 401 without creds → 200 with creds. ✅

So, given your app only has GET endpoints, your suite is accurately testing functionality in the correct layer.

Caveats (to stay compliant if you expand)

If you later add write endpoints (POST entry, POST like/comment/follow, etc.), you must add API-level tests for those user stories using the HTTP methods—not model calls.

Consider adding a few schema assertions on 200 responses (e.g., type, author, contentType, visibility) to show you’re testing the response shape, not only status codes and id.