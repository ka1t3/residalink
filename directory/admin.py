from django.contrib import admin
from .models import Contact, PracticalInfo, WorkRecord


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "phone", "residence")
    list_filter = ("category",)


@admin.register(WorkRecord)
class WorkAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "company", "amount", "residence")


@admin.register(PracticalInfo)
class PracticalInfoAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "residence")
    list_editable = ("order",)
