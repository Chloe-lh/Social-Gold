from django.contrib import admin
from .models import Author, Node
from golden.models import Author, Entry, Comment, Node, EntryImage, Follow, Inbox

"""
This module allows us to manipulate our database using the Django Admin panel.
"""

models_class = [Entry, Comment, Node, EntryImage, Follow, Inbox]
for model in models_class:
    admin.site.register(model)

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




