from django.shortcuts import render, redirect
from golden.models import Entry, Author
from golden.entry import EntryList

import uuid
import markdown 

# Create your views here.
def index(request):
    context = {}
    entries = Entry.objects.all()
    context['entries'] = entries
    return render(request, "index.html", context)

def home(request):
    context = {}
    form = Entry()
    entries = Entry.objects.all()
    context['entries'] = entries
    context['title'] = "Home"

    # User clicked the Post Button
    if request.method == "POST" and "entry_post" in request.POST:
        entry_id = "https://node1.com/api/entries/" + str(uuid.uuid4()), 

        # This is temporary because login feature doesn't exist yet
        if request.user.is_authenticated:
            try: 
                author = Author.objects.get(userName=request.user.username) 
            except:
                author = Author.objects.create(userName=request.user.username, password=request.user.password)

        markdown_content = request.POST['content']
        html_content = markdown.markdown(markdown_content)
        entry = Entry(
            id=entry_id,
            author=author, # type: ignore
            content=html_content,
            visibility=request.POST.get('visibility', 'PUBLIC')
        )
        entry.save()

        return redirect('home')
    
    # User clicks delete button
    if request.method == "POST" and "entry_delete" in request.POST:
        primary_key = request.POST.get('entry_delete')
        entry = Entry.objects.get(id=primary_key)
        entry.delete()
        return redirect('home')

    # User clicks the edit button
    if request.method == "POST" and "entry_edit" in request.POST:
        primary_key = request.POST.get('entry_edit')
        entry = Entry.objects.get(id=primary_key)
        form = EntryList(request.POST, instance=entry)
        entry.save()
    context['form'] = form 
    return render(request, "home.html", context)
