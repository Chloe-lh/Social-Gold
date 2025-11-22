from django.contrib.auth.forms import UserCreationForm
from .models import Author, Comment, Entry
from django import forms


class CustomUserForm(UserCreationForm):
    username = forms.CharField(max_length=100, required=True)
    password1 = forms.CharField(max_length=20, required=True)
    password2 = forms.CharField(max_length=20, required=True)

    class Meta(UserCreationForm.Meta):
        model = Author
        fields = ('username', 'password1', 'password2', 'name')

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ['name', 'profileImage', 'github', 'web', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'github': forms.URLInput(attrs={'class': 'form-input'}),
            'web': forms.URLInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'cols': 50}),
        }

class CommentForm(forms.ModelForm):
    content = forms.CharField(widget=forms.TextInput)
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(),
        }

class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ['content', 'author', 'is_posted', 'visibility']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
        }