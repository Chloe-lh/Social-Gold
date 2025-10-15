from django.contrib import admin
from golden.models import Author, Entry, Comments, Node

models_class = [Author, Entry, Comments, Node]

for model in models_class:
    admin.site.register(model)




