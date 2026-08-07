"""Envoi de notifications email. Synchrone : suffisant pour une résidence de 20 foyers."""
from django.conf import settings
from django.core.mail import send_mail

# kind -> champ de préférence utilisateur
KIND_FIELDS = {"incidents": "notify_incidents", "alerts": "notify_alerts", "replies": "notify_replies"}


def notify(users, subject, body, path="", kind=None):
    field = KIND_FIELDS.get(kind)
    recipients = [
        u.email for u in users
        if u.email and u.notify_by_email and (field is None or getattr(u, field, True))
    ]
    if not recipients:
        return
    link = f"\n\nVoir sur le site : {settings.SITE_URL}{path}"
    for r in recipients:  # envois individuels : pas de destinataires visibles entre voisins
        send_mail(subject, body + link, settings.DEFAULT_FROM_EMAIL, [r], fail_silently=True)
