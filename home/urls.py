# home/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'api/tfbs', views.TFBSViewSet, basename='tfbs')

urlpatterns = [
    path('', views.index, name='index'),
    path('search/', views.search_results, name='search_results'),
    path('api/tfbs/download/', views.download_results, name='download_results'),
    path('tfbs-details/<int:pk>/', views.tfbs_details, name='tfbs_details'),
    path('', include(router.urls)),
]