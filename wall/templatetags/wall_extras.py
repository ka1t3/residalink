import markdown, nh3
from django import template
from django.utils.safestring import mark_safe

register = template.Library()
_TAGS = {"strong", "em", "b", "i", "ul", "ol", "li", "p", "br", "a"}

@register.filter
def render_md(text):
    html = markdown.markdown(text or "", extensions=["nl2br"])
    clean = nh3.clean(html, tags=_TAGS, attributes={"a": {"href", "title"}}, link_rel="noopener noreferrer")
    return mark_safe(clean)