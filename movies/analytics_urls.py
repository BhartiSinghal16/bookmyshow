from django.urls import path
from movies import analytics_views

urlpatterns = [
    path('admin-dashboard/login/',       analytics_views.admin_login,        name='admin_login'),
    path('admin-dashboard/logout/',      analytics_views.admin_logout,       name='admin_logout'),
    path('admin-dashboard/',             analytics_views.analytics_dashboard, name='analytics_dashboard'),
    path('admin-dashboard/api/',         analytics_views.analytics_api,      name='analytics_api'),
    path('admin-dashboard/clear-cache/', analytics_views.clear_cache,        name='clear_cache'),
]