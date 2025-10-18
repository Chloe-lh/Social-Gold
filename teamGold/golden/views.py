from django.shortcuts import render
from golden.models import Entry
from golden.entry import EntryList

# Create your views here.
def index(request):
    context = {}
    entries = Entry.objects.all()
    context['entries'] = entries
    return render(request, "index.html", context)

def home(request):
    context = {}
    entry = EntryList()
    entries = Entry.objects.all()
    context['entries'] = entries
    context['title'] = "Home"
    context['entry'] = entry 
    return render(request, "home.html", context)

"""
def entry_post(request):

    if request.method == "POST":
        if 'entry_post' in request.POST: 
        
        elif 'entry_edit' in request.POST:

        elif 'entry_delete' in request.POST:
"""