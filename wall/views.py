from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from core.emails import notify
from core.models import User
from .models import Comment, Post, PostPhoto, Reaction


def _residence_posts(request):
    return Post.objects.filter(residence_id=request.user.residence_id)


@login_required
def post_list(request):
    posts = _residence_posts(request).select_related("author").prefetch_related("comments__author", "reactions__user", "photos")
    active_type = request.GET.get("type", "")
    if active_type:
        posts = posts.filter(type=active_type)
    return render(request, "wall/list.html", {"posts": posts, "types": Post.TYPES, "active_type": active_type})


@login_required
def post_create(request):
    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if content:
            post = Post.objects.create(
                residence_id=request.user.residence_id,
                author=request.user,
                type=request.POST.get("type", "info"),
                content=content,
                event_date=request.POST.get("event_date") or None,
                pinned=bool(request.POST.get("pinned")) and request.user.is_council,
            )
            for f in request.FILES.getlist("photos")[:3]:
                PostPhoto.objects.create(post=post, image=f)
            if post.type == "alerte":
                residents = User.objects.filter(residence_id=request.user.residence_id).exclude(pk=request.user.pk)
                notify(residents, f"[{post.residence.name}] Alerte : {post.content[:60]}",
                       f"{request.user.public_name} a publié une alerte :\n\n{post.content}", "/mur/", kind="alerts")
            messages.success(request, "Message publié")
    return redirect("post_list")


@login_required
def post_delete(request, pk):
    post = get_object_or_404(_residence_posts(request), pk=pk, author=request.user)
    if request.method == "POST":
        post.delete()
        messages.success(request, "Message supprimé")
    return redirect("post_list")


@login_required
def post_comment(request, pk):
    post = get_object_or_404(_residence_posts(request), pk=pk)
    content = request.POST.get("content", "").strip()
    if request.method == "POST" and content:
        Comment.objects.create(post=post, author=request.user, content=content)
        if post.author and post.author != request.user:
            notify([post.author], f"[{post.residence.name}] Réponse à votre message",
                   f"{request.user.public_name} a répondu :\n\n{content}", "/mur/", kind="replies")
    return redirect("post_list")


@login_required
def post_react(request, pk):
    post = get_object_or_404(_residence_posts(request), pk=pk)
    reaction, created = Reaction.objects.get_or_create(post=post, user=request.user)
    if not created:
        reaction.delete()
    return redirect("post_list")

@login_required
def post_edit(request, pk):
    post = get_object_or_404(_residence_posts(request), pk=pk, author=request.user)
    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if content:
            post.content = content
            post.type = request.POST.get("type", post.type)
            post.save()
            del_ids = request.POST.getlist("delete_photos")
            for photo in PostPhoto.objects.filter(pk__in=del_ids, post=post):
                photo.delete()
            remaining = 3 - post.photos.count()
            for f in request.FILES.getlist("photos")[:max(0, remaining)]:
                PostPhoto.objects.create(post=post, image=f)
            messages.success(request, "Message modifié")
            return redirect("post_list")
    return render(request, "wall/edit.html", {"post": post, "types": Post.TYPES})