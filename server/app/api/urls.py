# api/urls.py
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # Health check
    path('health/', views.health_check, name='health-check'),

    # Videos
    path('videos/', views.VideoListView.as_view(), name='video-list'),
    path('videos/upload/', views.VideoUploadView.as_view(), name='video-upload'),
    path('videos/<uuid:pk>/', views.VideoDetailView.as_view(), name='video-detail'),
    path('videos/delete/<uuid:pk>/', views.VideoDeleteView.as_view(), name='video-delete'),
    path('videos/update/<uuid:id>/', views.VideoUpdateView.as_view(), name='video-update'),
    path('videos/<uuid:video_id>/thumbnails/', views.ThumbnailListView.as_view(), name='thumbnail-list'),
    path('videos/<uuid:video_id>/transcript/', views.TranscriptDetailView.as_view(), name='transcript-detail'),
    path('videos/<uuid:video_id>/sections/', views.VideoSectionListView.as_view(), name='section-list'),
    path('videos/process/', views.VideoTaskTriggerView.as_view(), name='video-task-process'),

    # Episodes
    path('episodes/', views.EpisodeListView.as_view(), name='episode-list'),
    path('episodes/new/', views.EpisodeCreateView.as_view(), name='episode-new'),
    path('episodes/delete/<uuid:pk>/', views.EpisodeDeleteView.as_view(), name='episode-delete'),
    path('episodes/update/<uuid:id>/', views.EpisodeUpdateView.as_view(), name='episode-update'),
    path('episodes/<uuid:pk>/', views.EpisodeDetailView.as_view(), name='episode-detail'),

    # Tasks
    path('tasks/video/<uuid:pk>/', views.AsyncTaskItemsByVideoView.as_view(), name='task-list'),
    path('tasks/new/', views.AsyncTaskItemCreateView.as_view(), name='new-task-list'),
    path('tasks/<uuid:pk>/', views.AsyncTaskItemDetailView.as_view(), name='task-detail'),
]


# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
