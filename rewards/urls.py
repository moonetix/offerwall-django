from django.urls import path

from . import views

urlpatterns = [
    path("earn/", views.earn, name="earn"),
    path("earn/age/", views.confirm_age, name="earn-age"),
    # The trailing slash is part of the URL. Save it on the Postback page exactly like this,
    # or APPEND_SLASH answers 301 and Moonetix does not follow redirects.
    path("moonetix/postback/", views.moonetix_postback, name="moonetix-postback"),
]
