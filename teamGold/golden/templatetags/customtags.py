from django import template
register = template.Library()

@register.filter
def dictkey(dict_obj, key):
    return dict_obj.get(key)