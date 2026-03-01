from django.contrib.auth.forms import UserCreationForm
from django import forms

class RegisterForm(UserCreationForm):
    username = forms.UsernameField(label="username")
    password = forms.UsernameField(label="password")