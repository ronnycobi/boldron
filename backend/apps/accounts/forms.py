"""Forms bound to the email-based custom user model.

`RegistrationForm` is the public sign-up form; the `*User*Form` pair backs the
Django admin. Admin-only forms stay below.
"""
from django import forms
from django.contrib.auth.forms import (
    BaseUserCreationForm,
    UserChangeForm as BaseUserChangeForm,
)
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import User


class RegistrationForm(forms.Form):
    """Public self-serve registration: validates a unique email and a confirmed,
    policy-compliant password. Creating the org/credits account is left to the
    view (it owns those dependencies); `save()` just creates the User."""

    full_name = forms.CharField(max_length=255, required=False)
    email = forms.EmailField()
    org_name = forms.CharField(max_length=255, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with that email already exists. Try logging in instead."
            )
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        if p1 and not (p2 and p1 != p2):
            # Run the project's password policy, seeded with the user's own
            # attributes so the similarity check is meaningful.
            stub = User(
                email=cleaned.get("email") or "",
                full_name=cleaned.get("full_name") or "",
            )
            try:
                validate_password(p1, user=stub)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self) -> User:
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            full_name=self.cleaned_data.get("full_name", ""),
        )


class UserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name")
        field_classes = {"email": forms.EmailField}


class UserChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {"email": forms.EmailField}
