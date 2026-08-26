import time
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.core import mail, signing
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Residence, User


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
