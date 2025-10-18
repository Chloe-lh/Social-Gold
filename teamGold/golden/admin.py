from django.contrib import admin
from .models import Author, Node

# Register your models here.
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("userName", "is_admin", "is_approved")
    list_filter = ("is_admin", "is_approved")
    search_field = ('userName')
    actions = ['approve_authors']

    def approve_authors(self, request, queryset):
        queryset.update(is_approved=True)
    approve_authors.short_description = "Approve selected authors"

admin.site.register(Node)