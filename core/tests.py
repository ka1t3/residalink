import time
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.core import mail, signing
from django.db import OperationalError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import NotifiedError, PublicRequestCooldown, Residence, User
from .views import handler500


class MembersCouncilTests(TestCase):
    def setUp(self):
        self.residence = Residence.objects.create(name="Les Tilleuls")
        self.other_residence = Residence.objects.create(name="Les Peupliers")
        Group.objects.get_or_create(name="conseil_syndical")

    def _join(self, email, invite_code=None):
        return self.client.post(reverse("join"), {
            "invite_code": invite_code or self.residence.invite_code,
            "display_name": "Test",
            "email": email,
            "password1": "un-mot-de-passe-solide-123",
            "password2": "un-mot-de-passe-solide-123",
        })

    def test_premier_inscrit_rejoint_le_conseil_syndical(self):
        self._join("premier@example.com")
        user = User.objects.get(email="premier@example.com")
        self.assertTrue(user.is_council)

    def test_second_inscrit_ne_rejoint_pas_le_conseil_syndical(self):
        self._join("premier@example.com")
        self.client.logout()
        self._join("second@example.com")
        user = User.objects.get(email="second@example.com")
        self.assertFalse(user.is_council)

    def test_page_membres_404_pour_non_conseil(self):
        self._join("premier@example.com")  # devient CS
        self.client.logout()
        self._join("second@example.com")  # n'est pas CS
        resp = self.client.get(reverse("members_list"))
        self.assertEqual(resp.status_code, 404)

    def test_page_membres_ok_pour_conseil(self):
        self._join("premier@example.com")
        resp = self.client.get(reverse("members_list"))
        self.assertEqual(resp.status_code, 200)

    def test_promotion_et_retrait(self):
        self._join("premier@example.com")
        membre2 = User.objects.create_user(
            username="membre2@example.com", email="membre2@example.com",
            password="x", residence=self.residence, display_name="Membre 2",
        )
        resp = self.client.post(reverse("member_toggle_council", args=[membre2.pk]))
        self.assertEqual(resp.status_code, 302)
        membre2.refresh_from_db()
        self.assertTrue(membre2.is_council)

        resp = self.client.post(reverse("member_toggle_council", args=[membre2.pk]))
        membre2.refresh_from_db()
        self.assertFalse(membre2.is_council)

    def test_impossible_de_retirer_le_dernier_membre_du_cs(self):
        self._join("premier@example.com")
        premier = User.objects.get(email="premier@example.com")
        resp = self.client.post(reverse("member_toggle_council", args=[premier.pk]), follow=True)
        premier.refresh_from_db()
        self.assertTrue(premier.is_council)
        messages = [m.message for m in resp.context["messages"]]
        self.assertTrue(any("dernier membre" in m for m in messages))

    def test_post_forge_sur_membre_autre_residence_404(self):
        self._join("premier@example.com")
        intrus = User.objects.create_user(
            username="intrus@example.com", email="intrus@example.com",
            password="x", residence=self.other_residence, display_name="Intrus",
        )
        resp = self.client.post(reverse("member_toggle_council", args=[intrus.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_post_forge_par_non_conseil_404(self):
        self._join("premier@example.com")
        self.client.logout()
        self._join("second@example.com")
        second = User.objects.get(email="second@example.com")
        resp = self.client.post(reverse("member_toggle_council", args=[second.pk]))
        self.assertEqual(resp.status_code, 404)


class JoinDemoFlowTests(TestCase):
    """Un visiteur en session démo doit pouvoir rejoindre une vraie résidence
    avec un code, plutôt que d'être renvoyé dans la démonstration."""

    def setUp(self):
        self.demo_residence = Residence.objects.create(name="Résidence Démo", is_demo=True)
        self.demo_user = User.objects.create_user(
            username="demo", password="x", is_demo=True,
            residence=self.demo_residence, display_name="Démo",
        )
        self.real_residence = Residence.objects.create(name="Les Tilleuls")

    def test_visiteur_demo_est_deconnecte_et_voit_le_formulaire(self):
        self.client.force_login(self.demo_user)
        resp = self.client.get(reverse("join"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "core/join.html")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_utilisateur_reel_deja_connecte_est_renvoye_vers_son_espace(self):
        real_user = User.objects.create_user(
            username="reel", password="x", residence=self.real_residence, display_name="Réel",
        )
        self.client.force_login(real_user)
        resp = self.client.get(reverse("join"))
        self.assertRedirects(resp, reverse("home"), fetch_redirect_response=False)

    def test_visiteur_demo_peut_se_connecter_a_un_vrai_compte(self):
        """Le POST du formulaire de connexion ne doit jamais être bloqué par
        le middleware démo : sinon un visiteur en démo ne peut plus se
        connecter à son propre compte (message "modifications désactivées")."""
        real_user = User.objects.create_user(
            username="reel@example.com", email="reel@example.com", password="un-mot-de-passe-solide-123",
            residence=self.real_residence, display_name="Réel",
        )
        self.client.force_login(self.demo_user)
        resp = self.client.post(reverse("login"), {
            "username": "reel@example.com",
            "password": "un-mot-de-passe-solide-123",
        })
        self.assertEqual(int(self.client.session["_auth_user_id"]), real_user.pk)
        messages = [m.message for m in get_messages(resp.wsgi_request)]
        self.assertNotIn("Mode démonstration : les modifications sont désactivées.", messages)

    def test_bandeau_demo_propose_un_retour_a_l_accueil(self):
        self.client.force_login(self.demo_user)
        resp = self.client.get(reverse("home") + "?accueil=1")
        self.assertTemplateUsed(resp, "landing.html")

    def test_retour_a_l_accueil_visible_sur_les_pages_demo(self):
        self.client.force_login(self.demo_user)
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, "Retour à l'accueil")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Ma Résidence <no-reply@example.com>",
    SIGNUP_NOTIFY_EMAIL="admin@residalink.com",
)
class ContactFormTests(TestCase):

    @staticmethod
    def _ts(seconds_ago=10):
        return signing.TimestampSigner().sign(str(int(time.time()) - seconds_ago))

    def _post(self, **kwargs):
        data = {
            "name": "Test",
            "email": "visiteur@example.com",
            "message": "Bonjour",
            "ts": self._ts(),
        }
        data.update(kwargs)
        return self.client.post(reverse("contact"), data)

    def test_get_affiche_le_formulaire(self):
        resp = self.client.get(reverse("contact"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "core/contact.html")
        self.assertContains(resp, 'name="name"')
        self.assertContains(resp, 'name="ts"')

    def test_post_valide_envoie_le_mail_et_redirige(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("contact"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(m.to, [settings.SIGNUP_NOTIFY_EMAIL])
        self.assertEqual(m.reply_to, ["visiteur@example.com"])
        self.assertIn("Bonjour", m.body)

    def test_champs_obligatoires(self):
        resp = self._post(name="", email="", message="")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Le nom est obligatoire.")
        self.assertContains(resp, "L&#x27;e-mail est obligatoire.")
        self.assertContains(resp, "Le message est obligatoire.")
        self.assertEqual(len(mail.outbox), 0)

    def test_valeurs_conservees_en_erreur(self):
        resp = self._post(name="")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'value="visiteur@example.com"')
        self.assertContains(resp, "Bonjour")
        self.assertEqual(len(mail.outbox), 0)

    def test_email_invalide_rejete(self):
        resp = self._post(email="pas-un-email")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "n&#x27;est pas valide")
        self.assertEqual(len(mail.outbox), 0)

    def test_honeypot_rempli_abandon_silencieux(self):
        resp = self._post(website="spam")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_soumission_trop_rapide_abandon_silencieux(self):
        resp = self._post(ts=signing.TimestampSigner().sign(str(int(time.time()))))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_horodatage_forge_abandon_silencieux(self):
        resp = self._post(ts="zzz")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_message_utilisateur_echappe_pas_brut(self):
        resp = self._post(message="<script>alert(1)</script>", name="")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(resp, "<script>alert(1)</script>")

    def test_echec_envoi_message_d_erreur_et_valeurs_conservees(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("smtp down")):
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "L&#x27;envoi du message a échoué.")
        self.assertContains(resp, 'value="visiteur@example.com"')

    def test_visiteur_demo_peut_envoyer_un_message(self):
        demo_residence = Residence.objects.create(name="Résidence Démo", is_demo=True)
        demo_user = User.objects.create_user(
            username="demo-contact", password="x", is_demo=True,
            residence=demo_residence, display_name="Démo",
        )
        self.client.force_login(demo_user)
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)


class LoginThrottleTests(TestCase):
    """django-axes : 5 échecs → verrouillage du couple (email, IP) pendant 10 min."""

    FAILURE_LIMIT = 5

    def setUp(self):
        self.residence = Residence.objects.create(name="Les Tilleuls")
        self.user = User.objects.create_user(
            username="locataire@example.com",
            email="locataire@example.com",
            password="un-mot-de-passe-solide-123",
            residence=self.residence,
            display_name="Locataire",
        )
        self.ip = "203.0.113.7"

    def _login(self, username, password):
        return self.client.post(
            reverse("login"),
            {"username": username, "password": password},
            REMOTE_ADDR=self.ip,
        )

    def test_cinq_echecs_puis_verrouillage(self):
        # Les 4 premiers échecs : simple erreur de formulaire.
        for _ in range(self.FAILURE_LIMIT - 1):
            resp = self._login(self.user.username, "mot-de-passe-faux")
            self.assertEqual(resp.status_code, 200)

        # 5ᵉ échec : limite atteinte, message de verrouillage affiché.
        resp = self._login(self.user.username, "mot-de-passe-faux")
        self.assertEqual(resp.status_code, 429)
        self.assertTemplateUsed(resp, "core/axes_lockout.html")

        # Tentative suivante : toujours verrouillée, même avec le bon mot de passe.
        resp = self._login(self.user.username, "un-mot-de-passe-solide-123")
        self.assertEqual(resp.status_code, 429)

    def test_autre_adresse_nest_pas_verrouillee(self):
        for _ in range(self.FAILURE_LIMIT):
            self._login(self.user.username, "mot-de-passe-faux")

        autre = User.objects.create_user(
            username="autre@example.com", email="autre@example.com",
            password="un-mot-de-passe-solide-123",
            residence=self.residence, display_name="Autre",
        )
        resp = self._login(autre.username, "un-mot-de-passe-solide-123")
        self.assertEqual(resp.status_code, 302)

    def test_demo_pas_impacte_par_le_verrouillage(self):
        for _ in range(self.FAILURE_LIMIT):
            self._login(self.user.username, "mot-de-passe-faux")

        demo_residence = Residence.objects.create(name="Résidence Démo", is_demo=True)
        demo_user = User.objects.create_user(
            username="demo-throttle", password="x", is_demo=True,
            residence=demo_residence, display_name="Démo",
        )
        resp = self.client.get(reverse("demo"), REMOTE_ADDR=self.ip)
        self.assertEqual(resp.status_code, 302)


class ResidenceRequestThrottleTests(TestCase):
    """Demande de résidence : honeypot + délai signé + 1 demande / IP / heure."""

    def _ts(self, seconds_ago=10):
        return signing.TimestampSigner().sign(str(int(time.time()) - seconds_ago))

    def _post(self, ts=None, website="", **extra):
        data = {
            "name": "Camille",
            "email": "camille@example.com",
            "address": "12 rue de Lyon, 69003 Lyon",
            "role": "Copropriétaire",
            "message": "24 logements",
            "ts": ts if ts is not None else self._ts(),
            "website": website,
        }
        return self.client.post(reverse("residence_request"), data, **extra)

    def test_demande_valide_envoie_email(self):
        resp = self._post()
        self.assertRedirects(
            resp, f"{reverse('home')}?envoye=1#creer", fetch_redirect_response=False
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Demande de résidence", mail.outbox[0].subject)
        self.assertEqual(PublicRequestCooldown.objects.count(), 1)

    def test_honeypot_rempli_abandon_silencieux(self):
        resp = self._post(website="spam-bot")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PublicRequestCooldown.objects.count(), 0)

    def test_soumission_trop_rapide_abandon_silencieux(self):
        resp = self._post(ts=signing.TimestampSigner().sign(str(int(time.time()))))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_horodatage_forge_abandon_silencieux(self):
        resp = self._post(ts="zzz-invalid")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_deuxieme_demande_meme_ip_bloquee_sans_email(self):
        self._post()
        resp = self._post()
        self.assertRedirects(
            resp, f"{reverse('home')}?envoye=1#creer", fetch_redirect_response=False
        )
        self.assertEqual(len(mail.outbox), 1)  # seul le 1er e-mail est parti

    def test_autre_ip_autorisee(self):
        self._post()
        self._post(REMOTE_ADDR="203.0.113.8")
        self.assertEqual(len(mail.outbox), 2)

    def test_visiteur_demo_peut_envoyer_une_demande(self):
        demo_residence = Residence.objects.create(name="Résidence Démo", is_demo=True)
        demo_user = User.objects.create_user(
            username="demo-req", password="x", is_demo=True,
            residence=demo_residence, display_name="Démo",
        )
        self.client.force_login(demo_user)
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)


class PasswordValidatorTests(TestCase):
    """Validation des mots de passe : MinimumLengthValidator (8) +
    CommonPasswordValidator. Les 3 formulaires (inscription, réinitialisation,
    changement) refusent les mots courants ; create_user (démo, bootstrap)
    n'est pas concerné."""

    def setUp(self):
        self.residence = Residence.objects.create(name="Les Chênes")

    def _join(self, email, password1, password2=None):
        return self.client.post(reverse("join"), {
            "invite_code": self.residence.invite_code,
            "display_name": "Test",
            "email": email,
            "password1": password1,
            "password2": password2 or password1,
        })

    def test_inscription_mot_courant_refusee(self):
        resp = self._join("pv1@example.com", "motdepasse")
        self.assertEqual(resp.status_code, 200)  # formulaire re-affiché
        self.assertContains(resp, "Ce mot de passe est trop courant.")
        self.assertFalse(User.objects.filter(email="pv1@example.com").exists())

    def test_inscription_12345678_refusee(self):
        resp = self._join("pv2@example.com", "12345678")
        self.assertContains(resp, "Ce mot de passe est trop courant.")
        self.assertFalse(User.objects.filter(email="pv2@example.com").exists())

    def test_inscription_trop_court_refusee(self):
        resp = self._join("pv3@example.com", "abc123!")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "trop court")
        self.assertFalse(User.objects.filter(email="pv3@example.com").exists())

    def test_inscription_mot_memoire_acceptee(self):
        resp = self._join("pv4@example.com", "ma-residence-bleue-42")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(email="pv4@example.com").exists())

    def test_reinitialisation_mot_courant_refuse(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        user = User.objects.create_user(
            username="pv5@example.com", email="pv5@example.com",
            password="ancien-mot-de-passe-solide-9",
            residence=self.residence, display_name="R",
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url = reverse("password_reset_confirm", args=[uidb64, token])
        # Django 6 : le token est stocké en session, la vue redirige vers
        # l'URL avec reset_url_token (set-password) ; on suit la redirection.
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        set_password_url = resp.headers["Location"]
        resp = self.client.post(set_password_url, {
            "new_password1": "motdepasse",
            "new_password2": "motdepasse",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ce mot de passe est trop courant.")
        user.refresh_from_db()
        self.assertTrue(user.check_password("ancien-mot-de-passe-solide-9"))

    def test_changement_mdp_mot_courant_refuse(self):
        user = User.objects.create_user(
            username="pv6@example.com", email="pv6@example.com",
            password="ancien-mot-de-passe-solide-9",
            residence=self.residence, display_name="P",
        )
        self.client.force_login(user)
        resp = self.client.post(reverse("password_change"), {
            "old_password": "ancien-mot-de-passe-solide-9",
            "new_password1": "motdepasse",
            "new_password2": "motdepasse",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ce mot de passe est trop courant.")
        user.refresh_from_db()
        self.assertTrue(user.check_password("ancien-mot-de-passe-solide-9"))

    def test_create_user_pas_valide_par_les_validateurs(self):
        # create_user (bootstrap, admin) et set_unusable_password (démo) ne
        # passent pas par les validateurs : un mot « faible » peut être posé
        # par l'opérateur sans blocage.
        u = User.objects.create_user(
            username="pv7@example.com", email="pv7@example.com",
            password="password", residence=self.residence, display_name="A",
        )
        self.assertIsNotNone(u.pk)
        u.set_unusable_password()
        u.save()
        self.assertFalse(u.has_usable_password())
class Error500NotificationTests(TestCase):
    """handler500 : page polie + e-mail opérateur, 1 e-mail / heure / signature."""

    def _call_500(self, exc=None, path="/mur/"):
        """Simule l'appel de handler500 depuis un bloc except (exc_info actif)."""
        factory = RequestFactory()
        request = factory.get(path)
        try:
            raise exc or ValueError("boom-test")
        except Exception:
            return handler500(request)

    def test_500_page_polie_et_email_opérateur(self):
        resp = self._call_500()
        self.assertEqual(resp.status_code, 500)
        # pas de fuite d'info technique dans la page
        body = resp.content.decode()
        self.assertIn("Une erreur est survenue", body)  # template core/error500.html
        self.assertIn("Retour à l'accueil", body)
        self.assertNotIn("boom-test", body)
        self.assertNotIn("Traceback", body)
        # e-mail à l'opérateur
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Erreur 500", email.subject)
        self.assertEqual(email.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(email.to, [settings.ERROR_NOTIFY_EMAIL])
        # contexte dans le corps
        self.assertIn("boom-test", email.body)
        self.assertIn("GET", email.body)
        self.assertIn("anonyme", email.body)

    def test_500_deduplication_meme_signature(self):
        self._call_500()
        self._call_500()
        self.assertEqual(len(mail.outbox), 1)
        entry = NotifiedError.objects.get()
        self.assertEqual(entry.count, 2)

    def test_500_nouvelle_signature_notifie_de_nouveau(self):
        self._call_500(exc=ValueError("boom-A"))
        self._call_500(exc=RuntimeError("boom-B"))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(NotifiedError.objects.count(), 2)

    def test_500_renotification_apres_une_heure(self):
        self._call_500()
        NotifiedError.objects.update(
            last_notified_at=timezone.now() - timedelta(hours=1, minutes=1)
        )
        self._call_500()
        self.assertEqual(len(mail.outbox), 2)

    def test_500_utilisateur_connecte_en_reply_to(self):
        user = User.objects.create_user(
            username="test-500", password="x", email="user500@example.com",
            residence=Residence.objects.create(name="T500"), display_name="T",
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        try:
            raise ValueError("boom-auth")
        except Exception:
            resp = handler500(request)
        self.assertEqual(resp.status_code, 500)
        email = mail.outbox[0]
        self.assertEqual(email.extra_headers.get("Reply-To"), "user500@example.com")

    def test_500_purge_entrées_obsolètes(self):
        NotifiedError.objects.create(
            signature="old", last_notified_at=timezone.now() - timedelta(days=8), count=1,
        )
        self._call_500()
        # l'entrée vieille de 8 jours a été purgée, la nouvelle reste
        self.assertEqual(NotifiedError.objects.count(), 1)
        self.assertNotEqual(NotifiedError.objects.get().signature, "old")

    def test_404_ne_notifie_pas(self):
        resp = self.client.get("/une-route-inexistante/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_wiring_resolver_500_pointeur_handler(self):
        """Django 6 résout le handler 500 depuis le module urlconf (config/urls.py),
        pas depuis un réglage HANDLERS. On vérifie que le pointeur est bien notre vue."""
        from django.urls import get_resolver
        callback = get_resolver().resolve_error_handler(500)
        self.assertIs(callback, handler500)

    @override_settings(DEBUG=False)
    def test_500_e2e_exposition_complete(self):
        """Exception réelle levée dans une vue, stack complète (middleware →
        resolve_error_handler → handler500), DEBUG=False.

        Vérifie : 500 + page polie + e-mail opérateur + pas de fuite d'info.
        """
        from django.urls import path
        from django.test import Client
        import config.urls as urls

        def boom(request):
            raise ValueError("explosion-e2e")

        urls.urlpatterns.append(path("e2e-boom/", boom))
        try:
            client = Client(raise_request_exception=False)
            resp = client.get("/e2e-boom/")
        finally:
            urls.urlpatterns.pop()

        self.assertEqual(resp.status_code, 500)
        body = resp.content.decode()
        self.assertIn("Une erreur est survenue", body)
        self.assertNotIn("explosion-e2e", body)   # pas de fuite dans la page
        self.assertNotIn("Traceback", body)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("explosion-e2e", mail.outbox[0].body)  # traceback dans l'e-mail
class OpenRegistrationTests(TestCase):
    """Mode résidence unique (OPEN_REGISTRATION=False) : parcours SaaS masqué."""

    @override_settings(OPEN_REGISTRATION=True)
    def test_saaS_default_landing_avec_formulaire(self):
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Créer l'espace de ma résidence")
        self.assertContains(resp, 'name="ts"')

    @override_settings(OPEN_REGISTRATION=False)
    def test_landing_sans_formulaire_avec_cta_rejoindre(self):
        resp = self.client.get(reverse("home"))
        self.assertNotContains(resp, "Créer l'espace de ma résidence")
        self.assertNotContains(resp, 'name="ts"')
        self.assertContains(resp, "/rejoindre/")

    @override_settings(OPEN_REGISTRATION=False)
    def test_demande_residence_404_get(self):
        resp = self.client.get(reverse("residence_request"))
        self.assertEqual(resp.status_code, 404)

    @override_settings(OPEN_REGISTRATION=False)
    def test_demande_residence_404_post(self):
        resp = self.client.post(reverse("residence_request"), {
            "name": "X", "email": "x@x.com", "address": "y", "ts": "", "website": "",
        })
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(OPEN_REGISTRATION=False)
    def test_rejoindre_toujours_functionnel(self):
        residence = Residence.objects.create(name="Les Tilleuls")
        resp = self.client.post(reverse("join"), {
            "invite_code": residence.invite_code,
            "display_name": "Test",
            "email": "test@example.com",
            "password1": "un-mot-de-passe-solide-123",
            "password2": "un-mot-de-passe-solide-123",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(User.objects.count(), 1)

    @override_settings(OPEN_REGISTRATION=False)
    def test_pages_contact_confidentialite_ok(self):
        for name in ("contact", "privacy", "terms", "login"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
class HealthzTests(TestCase):
    """Endpoint de santé /healthz : vérifie la base, répond sans info sensible."""

    def test_healthz_ok(self):
        resp = self.client.get(reverse("healthz"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_healthz_db_down(self):
        with mock.patch(
            "django.db.connection.cursor", side_effect=OperationalError("db down")
        ):
            resp = self.client.get(reverse("healthz"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {"status": "error"})

    def test_healthz_pas_de_fuite_d_info(self):
        resp = self.client.get(reverse("healthz"))
        self.assertNotIn("django", resp.content.decode().lower())
        self.assertNotIn("secret", resp.content.decode().lower())
