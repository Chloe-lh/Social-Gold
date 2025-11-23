from django.contrib import admin
from .models import Author, Node
from golden.models import Author, Entry, Comment, Node, EntryImage, Follow, Inbox

"""
This module allows us to manipulate our database using the Django Admin panel.
"""

models_class = [Entry, Comment, EntryImage, Inbox]
for model in models_class:
    admin.site.register(model)

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """
    Admin interface for Follow objects.
    Shows usernames for both local and remote authors.
    """
    list_display = ("id", "get_actor_username", "get_object_username", "state", "published")
    list_filter = ("state", "published")
    search_fields = ("id", "summary", "actor__username", "object")
    readonly_fields = ("id", "published", "get_actor_username", "get_object_username")
    
    fieldsets = (
        ("Follow Information", {
            "fields": ("id", "summary", "state", "published")
        }),
        ("Actors", {
            "fields": ("actor", "get_actor_username", "object", "get_object_username"),
            "description": "Actor is the person making the follow request. Object is the person being followed."
        }),
    )
    
    def get_actor_username(self, obj):
        """Display actor username"""
        if obj.actor:
            return f"{obj.actor.username} ({obj.actor.id})"
        return "Unknown"
    get_actor_username.short_description = "Actor (Username)"
    
    def get_object_username(self, obj):
        """Display object username by looking up the author by FQID"""
        from golden.models import Author
        from golden.services import normalize_fqid, get_or_create_foreign_author
        
        if not obj.object:
            return "None"
        
        # Try to find the author by FQID
        object_id = normalize_fqid(str(obj.object))
        author = Author.objects.filter(id=object_id).first()
        
        if not author:
            # Try without normalization
            author = Author.objects.filter(id=str(obj.object).rstrip('/')).first()
        
        if not author:
            # Try to fetch and create the remote author if it doesn't exist
            try:
                author = get_or_create_foreign_author(str(obj.object))
            except Exception as e:
                # If we can't fetch, just show the FQID
                return f"Not found: {obj.object}"
        
        if author:
            return f"{author.username} ({author.id})"
        else:
            # Author not in database yet - return just the FQID
            return f"Not found: {obj.object}"
    get_object_username.short_description = "Object (Username)"

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    """
    Admin interface for Node management.
    Makes it easy to see which nodes are active and configure authentication.
    """
    list_display = ("id", "title", "is_active", "auth_user", "description")
    list_filter = ("is_active",)
    search_fields = ("id", "title", "description")
    list_editable = ("is_active",)  # Allow quick toggle of is_active
    
    fieldsets = (
        ("Node Information", {
            "fields": ("id", "title", "description", "is_active")
        }),
        ("Authentication", {
            "fields": ("auth_user", "auth_pass"),
            "description": "HTTP Basic Auth credentials for accessing this node's API"
        }),
        ("Administrators", {
            "fields": ("admins",),
            "description": "Local authors who can manage this node"
        }),
    )

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    '''
    Class to add additional functionality to the Admin Author section, 
    with the key feature of allowing admins to approve users.
    '''
    list_display = ("username", "is_admin", "is_approved")
    list_filter = ("is_admin", "is_approved")
    search_field = ('username')
    actions = ['approve_authors']

    def approve_authors(self, request, queryset):
        queryset.update(is_approved=True)
    approve_authors.short_description = "Approve selected authors"




