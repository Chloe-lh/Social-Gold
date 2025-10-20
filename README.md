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
- GET /api/Profile/<id>/
- GET /api/Entry/<id>/
- GET /api/Node/<id>/
- GET /api/Follow/<id>/
- GET /api/Like/<id>/
- GET /api/Comment/<id>/
- GET /api/EntryImage/<id>/
> **Note:** <id> in most endpoints accepts a full path (<path:id>), which allows slashes/URLs. EntryImage requires an integer.

### Authentication (HTTP Basic Auth)
Scheme: HTTP Basic Auth

