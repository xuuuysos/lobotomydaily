# pylint: disable=too-many-ancestors
"""
Forms for user registration.
"""

from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class RegisterForm(UserCreationForm):
    """
    Form for new user registration inheriting from UserCreationForm.
    """
    class Meta:
        """
        Meta options mapping User model fields to the registration form.
        """
        model = User
        fields = ("username",)
