from django import forms
from golden.models import Entry, Comment

class EntryList(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ['content', 'author', 'is_posted', 'visibility']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
        }

