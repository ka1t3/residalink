from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path, reverse_lazy
from django.views.static import serve
from core import views as core
from directory import views as directory
from incidents import views as incidents
from wall import views as wall
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", core.home, name="home"),
    path("demo/", core.demo, name="demo"),
    path("demande-residence/", core.residence_request, name="residence_request"),
    path("contact/", core.contact, name="contact"),
    path("sw.js", core.service_worker, name="sw"),
    path("favicon.ico", core.favicon, name="favicon"),
    path("rejoindre/", core.join, name="join"),
    path("connexion/", auth_views.LoginView.as_view(template_name="core/login.html"), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("profil/", core.profile, name="profile"),
    path("membres/", core.members_list, name="members_list"),
    path("membres/<int:pk>/conseil/", core.member_toggle_council, name="member_toggle_council"),
    path("recherche/", core.search, name="search"),
    path("profil/mot-de-passe/", core.password_change, name="password_change"),
    path("mot-de-passe-oublie/", auth_views.PasswordResetView.as_view(
        template_name="core/password_reset_form.html",
        email_template_name="core/password_reset_email.txt",
        subject_template_name="core/password_reset_subject.txt",
        success_url=reverse_lazy("password_reset_done")), name="password_reset"),
    path("mot-de-passe-oublie/envoye/", auth_views.PasswordResetDoneView.as_view(
        template_name="core/password_reset_done.html"), name="password_reset_done"),
    path("reinitialiser/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="core/password_reset_confirm.html",
        success_url=reverse_lazy("password_reset_complete")), name="password_reset_confirm"),
    path("reinitialiser/termine/", auth_views.PasswordResetCompleteView.as_view(
        template_name="core/password_reset_complete.html"), name="password_reset_complete"),
    path("incidents/", incidents.incident_list, name="incident_list"),
    path("incidents/nouveau/", incidents.incident_new, name="incident_new"),
    path("incidents/<int:pk>/", incidents.incident_detail, name="incident_detail"),
    path("incidents/<int:pk>/suivre/", incidents.incident_follow, name="incident_follow"),
    path("incidents/<int:pk>/maj/", incidents.incident_update, name="incident_update"),
    path("mur/", wall.post_list, name="post_list"),
    path("mur/publier/", wall.post_create, name="post_create"),
    path("mur/<int:pk>/supprimer/", wall.post_delete, name="post_delete"),
    path("mur/<int:pk>/commenter/", wall.post_comment, name="post_comment"),
    path("mur/<int:pk>/reagir/", wall.post_react, name="post_react"),
    path("carnet/", directory.directory_home, name="directory_home"),
    path("carnet/<str:kind>/nouveau/", directory.item_edit, name="carnet_new"),
    path("carnet/<str:kind>/<int:pk>/", directory.item_edit, name="carnet_edit"),
    path("carnet/<str:kind>/<int:pk>/supprimer/", directory.item_delete, name="carnet_delete"),
    path("confidentialite/", TemplateView.as_view(template_name="legal/privacy.html"), name="privacy"),
    path("mentions-legales/", TemplateView.as_view(template_name="legal/terms.html"), name="terms"),
    path("mur/<int:pk>/modifier/", wall.post_edit, name="post_edit"),
    path("incidents/<int:pk>/modifier/", incidents.incident_edit, name="incident_edit"),
]

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

# Handler d'erreur 500 en production (page polie + e-mail à l'opérateur, 1 e-mail
# maximum par heure par signature d'erreur). En DEBUG (développement), Django
# affiche sa page technique avant même de résoudre ce handler.
handler500 = core.handler500
