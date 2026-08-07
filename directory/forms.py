from django import forms
from .models import Contact, PracticalInfo, WorkRecord


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ("category", "name", "role", "phone", "email", "notes")


class PracticalInfoForm(forms.ModelForm):
    class Meta:
        model = PracticalInfo
        fields = ("title", "content", "order")


class WorkRecordForm(forms.ModelForm):
    class Meta:
        model = WorkRecord
        fields = ("title", "date", "company", "amount", "description")
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
