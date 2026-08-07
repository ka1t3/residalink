from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Residence, User


class JoinForm(UserCreationForm):
    invite_code = forms.CharField(label="Code résidence", max_length=12)
    email = forms.EmailField(label="Email")

    class Meta:
        model = User
        fields = ("invite_code", "display_name", "lot", "email", "password1", "password2")
        labels = {"display_name": "Votre nom", "lot": "Lot / appartement (facultatif)"}

    def clean_invite_code(self):
        code = self.cleaned_data["invite_code"].strip().upper()
        try:
            self.residence = Residence.objects.get(invite_code=code)
        except Residence.DoesNotExist:
            raise forms.ValidationError("Code inconnu. Vérifiez le courrier reçu dans votre boîte aux lettres.")
        return code

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet email.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.residence = self.residence
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name", "lot", "notify_by_email", "notify_incidents", "notify_alerts", "notify_replies")
        labels = {"display_name": "Votre nom", "lot": "Lot / appartement"}
