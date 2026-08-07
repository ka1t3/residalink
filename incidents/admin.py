from django.contrib import admin
from .models import Incident, IncidentCategory, IncidentUpdate


@admin.register(IncidentCategory)
class IncidentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "order")
    list_editable = ("icon", "order")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "residence", "created_at")
    list_filter = ("status", "category")


admin.site.register(IncidentUpdate)
