from django.contrib import admin
from .models import Author, Node
from golden.models import Author, Entry, Comment, Node

models_class = [Author, Entry, Comment, Node]

for model in models_class:
    if model is not Author:
        admin.site.register(model)

'''
class to add additional functionality to the Admin Author section
Allows admin to approve users
'''
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("username", "is_admin", "is_approved")
    list_filter = ("is_admin", "is_approved")
    search_field = ('username')
    actions = ['approve_authors']

    def approve_authors(self, request, queryset):
        queryset.update(is_approved=True)
    approve_authors.short_description = "Approve selected authors"

