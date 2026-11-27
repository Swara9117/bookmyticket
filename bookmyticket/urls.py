from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from movies import views as movie_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('', include('users.urls')),
    path('movies/', include('movies.urls')),
    path('dashboard/', movie_views.dashboard, name='dashboard'),
    path('dashboard/export/', movie_views.export_dashboard, name='export_dashboard'),
    path('internal/jobs/', movie_views.run_jobs, name='run_jobs'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)