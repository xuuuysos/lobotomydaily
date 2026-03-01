import django.contrib.auth.forms as f

class RegisterForm(f.UserCreationForm):
    username = f.forms.CharField(label="username")
    password = f.forms.CharField(label="password")