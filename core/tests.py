from django.contrib.auth.models import Group
from django.test import TestCase
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
