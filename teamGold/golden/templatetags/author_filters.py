from django import template
from golden.services import fqid_to_uuid, is_local

register = template.Library()

@register.filter
def author_url_id(author_id):
    """
    Get URL-friendly identifier for an author ID.
    For local authors: returns UUID part
    For remote authors: returns full FQID
    """
    if not author_id:
        return None
    
    author_id_str = str(author_id)
    if is_local(author_id_str):
        # Local author - use UUID for cleaner URLs
        return fqid_to_uuid(author_id_str)
    else:
        # Remote author - use full FQID
        return author_id_str.rstrip('/')

