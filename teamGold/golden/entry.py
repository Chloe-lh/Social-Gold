from django import forms
from golden.models import Entry

class EntryList(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ['author', 'content', 'likes']

        



