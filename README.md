[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/etkNZkSE)
CMPUT404-project-socialdistribution
===================================

CMPUT404-project-socialdistribution

See [the web page](https://uofa-cmput404.github.io/general/project.html) for a description of the project.

Make a distributed social network!

## Copyright
**Team Members:**
- Aesoji
- chobo
- Emoji_King
- Irisveil
- Pooja
- zaara

## License

* Choose an OSI approved license, name it here, and copy the license text to a file called `LICENSE`.
---
  
## API Access Information
### Service Details
| Setting | Value |
|----------------|-----------------------------|
| **Hostname** | `localhost` |
| **Port** | `8000` |
| **Protocol** | `http` / `https` |
| **Base URL** | `http://localhost:8000/` |
| **URL Prefix** | `/api/` |


### Golden's Available Endpoints
- GET  /api/Profile/<path:id>/
- GET  /api/Node/<path:id>/
- POST /api/authors/<path:author_serial>/inbox/
- POST /api/author/<uuid:author_id>/inbox/
- GET  /api/Entry/<path:id>/
- POST /api/entries/<uuid:entry_id>/
- GET  /api/entries/<path:entry_fqid>/comments/
- GET  /api/Entry/<path:entry_id>/comments/
- GET  /api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/
- POST /api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/
- GET  /api/authors/<str:author_id>/entries/<str:entry_id>/comments/<path:comment_fqid>/
- GET  /api/Like/<path:id>/
- GET  /api/Follow/<path:id>/
- GET  /api/Author/<path:author_id>/friends/
- GET  /api/EntryImage/<int:id>/
- POST /api/Entry/<path:entry_id>/images/

### Authentication (HTTP Basic Auth)
Scheme: HTTP Basic Auth
*Remote nodes must authenticate to prior to being able to send inbox POST, access entries, and use the website.*
