from django.contrib.auth.forms import UserCreationForm
from .models import Author, Comments
from django import forms

class CustomUserForm(UserCreationForm):
    username = forms.CharField(max_length=100, required=True)
    password1 = forms.CharField(max_length=20, required=True)
    password2 = forms.CharField(max_length=20, required=True)

    class Meta(UserCreationForm.Meta):
        model = Author
        fields = ('username', 'password1', 'password2')

class CustomCommentForm(forms.ModelForm):

    class Meta(forms.ModelForm.Meta):
        model = Comments
        fields = ('comment', 'contentType')

