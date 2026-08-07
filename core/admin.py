from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import Residence, ResidenceModule, User


class ModuleInline(admin.TabularInline):
    model = ResidenceModule
    extra = 0


@admin.register(Residence)
class ResidenceAdmin(admin.ModelAdmin):
    list_display = ("name", "invite_code", "created_at")
    inlines = [ModuleInline]


class AdminUserCreateForm(UserCreationForm):
    """Création depuis l'admin : email et mot de passe obligatoires.
    L'identifiant de connexion (username) est automatiquement l'email,
    comme pour les inscriptions via le code résidence."""

    class Meta:
        model = User
        fields = ("email", "display_name", "lot", "residence")

    email = forms.EmailField(label="Email", required=True)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet email.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class AdminUserChangeForm(UserChangeForm):
    """Modification depuis l'admin : l'email reste obligatoire."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = AdminUserCreateForm
    form = AdminUserChangeForm
    list_display = ("display_name", "email", "lot", "residence", "is_staff")
    fieldsets = UserAdmin.fieldsets + (("Résidence", {"fields": ("residence", "display_name", "lot", "notify_by_email")}),)
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "display_name", "lot", "residence", "password1", "password2"),
        }),
    )
