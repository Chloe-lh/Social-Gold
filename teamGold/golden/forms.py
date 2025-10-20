from django.contrib.auth.forms import UserCreationForm
from .models import Author
from django import forms

class CustomUserForm(UserCreationForm):
    username = forms.CharField(max_length=100, required=True)
    password1 = forms.CharField(max_length=20, required=True)
    password2 = forms.CharField(max_length=20, required=True)

    class Meta(UserCreationForm.Meta):
        model = Author
        fields = ('username', 'password1', 'password2')

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ['username', 'profileImage', 'github', 'web']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'github': forms.URLInput(attrs={'class': 'form-input'}),
            'web': forms.URLInput(attrs={'class': 'form-input'}),
        }