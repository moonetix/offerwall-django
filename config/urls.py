from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="earn", permanent=False)),
    # Demo sign-in with Django's built-in views. Keep your own authentication in your project.
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("", include("rewards.urls")),
]
