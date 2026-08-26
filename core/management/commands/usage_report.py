"""Rapport d'usage par résidence — LECTURE SEULE (aucune écriture en base).

Usage :
    uv run manage.py usage_report
    uv run manage.py usage_report --residence 1
    uv run manage.py usage_report --csv
"""
import csv
import io

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Residence, User
from incidents.models import Incident, IncidentUpdate
from wall.models import Comment, Post

VERDICT_RANK = {"SIGNAL FORT": 4, "SIGNAL RÉEL": 3, "SIGNAL FAIBLE": 2, "AUCUN USAGE": 1, "NON CLASSÉ": 0}


class Command(BaseCommand):
    help = "Mesure l'usage réel de chaque résidence (exclusion des résidences et comptes de démo)."

    def add_arguments(self, parser):
        parser.add_argument("--residence", type=int, default=None, help="Restreindre à un identifiant de résidence.")
        parser.add_argument("--csv", action="store_true", help="Sortie CSV au lieu du tableau texte.")

    def handle(self, *args, **options):
        residences = Residence.objects.filter(is_demo=False).order_by("id")
        if options["residence"] is not None:
            residences = residences.filter(pk=options["residence"])

        rows = [self._measure(r) for r in residences]
        if options["csv"]:
            self._write_csv(rows)
        else:
            self._write_text(rows)

    def _measure(self, residence):
        valid_users = User.objects.filter(residence=residence, is_demo=False, is_staff=False)

        incidents = Incident.objects.filter(residence=residence, author__in=valid_users)
        posts = Post.objects.filter(residence=residence, author__in=valid_users)
        comments = Comment.objects.filter(post__residence=residence, author__in=valid_users)

        author_ids = set(incidents.values_list("author_id", flat=True))
        author_ids |= set(posts.values_list("author_id", flat=True))
        author_ids |= set(comments.values_list("author_id", flat=True))
        author_ids.discard(None)
        n1 = len(author_ids)

        timestamps = list(incidents.values_list("created_at", flat=True))
        timestamps += list(posts.values_list("created_at", flat=True))
        timestamps += list(comments.values_list("created_at", flat=True))
        weeks = {(t.isocalendar()[0], t.isocalendar()[1]) for t in timestamps}
        n2 = len(weeks)
        last_content = max(timestamps) if timestamps else None
        days_since = (timezone.now() - last_content).days if last_content else None

        changes = IncidentUpdate.objects.filter(
            incident__residence=residence,
            author__in=valid_users,
            incident__author__isnull=False,
            incident__author__in=valid_users,
        ).exclude(old_status="").exclude(new_status="").select_related(
            "incident", "incident__author", "author"
        ).order_by("incident_id")

        incidents_n4 = {}
        for u in changes:
            if u.old_status == u.new_status:
                continue
            if u.author_id == u.incident.author_id:
                continue
            incidents_n4.setdefault(u.incident_id, {
                "incident": u.incident,
                "reporter": u.incident.author,
                "changers": set(),
            })["changers"].add(u.author)
        n4 = len(incidents_n4)

        verdict = "NON CLASSÉ"
        if n1 <= 1:
            verdict = "AUCUN USAGE"
        if n1 >= 3 and n2 < 3 and VERDICT_RANK[verdict] < 2:
            verdict = "SIGNAL FAIBLE"
        if n1 >= 3 and n2 >= 3 and VERDICT_RANK[verdict] < 3:
            verdict = "SIGNAL RÉEL"
        if n4 >= 1 and VERDICT_RANK[verdict] < 4:
            verdict = "SIGNAL FORT"

        return {
            "residence_id": residence.id,
            "name": residence.name,
            "created_at": timezone.localtime(residence.created_at),
            "comptes": residence.members.count(),
            "n1": n1,
            "n2": len(weeks),
            "n3": timezone.localtime(last_content) if last_content else None,
            "days_since": days_since,
            "n4": n4,
            "incidents_n4": incidents_n4,
            "verdict": verdict,
        }

    def _user_label(self, user):
        if user is None:
            return "inconnu (compte supprimé)"
        return f"{user.display_name or user.username} (#{user.pk})"

    def _write_text(self, rows):
        for r in rows:
            self.stdout.write(f"Résidence : {r['name']} (id={r['residence_id']})")
            self.stdout.write(f"  Créée le   : {r['created_at']:%Y-%m-%d %H:%M}")
            self.stdout.write(f"  Comptes    : {r['comptes']}")
            self.stdout.write(f"  N1 comptes distincts ayant produit : {r['n1']}")
            self.stdout.write(f"  N2 semaines calendaires distinctes: {r['n2']}")
            if r["n3"] is not None:
                self.stdout.write(f"  N3 dernier contenu : {r['n3']:%Y-%m-%d %H:%M} (il y a {r['days_since']} jour{'s' if r['days_since'] > 1 else ''})")
            else:
                self.stdout.write("  N3 dernier contenu : aucun")
            self.stdout.write(f"  N4 incidents repris par un tiers   : {r['n4']}")
            if r["incidents_n4"]:
                for entry in r["incidents_n4"].values():
                    changers = ", ".join(sorted(self._user_label(c) for c in entry["changers"]))
                    inc = entry["incident"]
                    self.stdout.write(
                        f"      #{inc.pk}  {inc.title[:50]:<50}  "
                        f"signalé par {self._user_label(entry['reporter'])} — changé par {changers}"
                    )
            else:
                self.stdout.write("      (aucun incident concerné)")
            verdict = r["verdict"]
            if verdict == "SIGNAL FORT":
                self.stdout.write(f"  Verdict    : {self.style.SUCCESS(verdict)}")
            elif verdict in ("SIGNAL RÉEL", "SIGNAL FAIBLE"):
                self.stdout.write(f"  Verdict    : {self.style.WARNING(verdict)}")
            else:
                self.stdout.write(f"  Verdict    : {verdict}")
            self.stdout.write("")

        non_classed = [r for r in rows if r["verdict"] == "NON CLASSÉ"]
        if non_classed:
            self.stdout.write(self.style.WARNING(
                "Attention : " + ", ".join(f"{r['name']} (id={r['residence_id']}, N1={r['n1']})" for r in non_classed)
                + " n'a aucun des seuils du barème atteint (N1=2 sans N4) — verdict « NON CLASSÉ »."
            ))

    def _write_csv(self, rows):
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["residence_id", "nom", "cree_le", "comptes", "N1", "N2", "N3_dernier_contenu", "N3_jours_depuis", "N4", "incidents_N4", "verdict"])
        for r in rows:
            incidents = []
            for entry in r["incidents_n4"].values():
                inc = entry["incident"]
                changers = ", ".join(sorted(self._user_label(c) for c in entry["changers"]))
                incidents.append(f"#{inc.pk}: {inc.title[:50]} | signalé par {self._user_label(entry['reporter'])} -> {changers}")
            writer.writerow([
                r["residence_id"], r["name"],
                r["created_at"].isoformat() if r["created_at"] else "",
                r["comptes"], r["n1"], r["n2"],
                r["n3"].isoformat() if r["n3"] else "",
                r["days_since"] if r["days_since"] is not None else "",
                r["n4"], "; ".join(incidents), r["verdict"],
            ])
        self.stdout.write(out.getvalue().rstrip("\n"))
