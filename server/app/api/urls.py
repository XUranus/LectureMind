# api/urls.py
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('health/', views.health_check, name='health-check'),

    # Videos
    path('videos/', views.VideoListView.as_view(), name='video-list'),
    path('videos/upload/', views.VideoUploadView.as_view(), name='video-upload'),
    path('videos/<uuid:pk>/', views.VideoDetailView.as_view(), name='video-detail'),
    path('videos/delete/<uuid:pk>/', views.VideoDeleteView.as_view(), name='video-delete'),
    path('videos/update/<uuid:id>/', views.VideoUpdateView.as_view(), name='video-update'),
    path('videos/<uuid:video_id>/thumbnails/', views.ThumbnailListView.as_view(), name='thumbnail-list'),
    path('videos/<uuid:video_id>/slide-ocr/', views.SlideOCRListView.as_view(), name='slide-ocr-list'),
    path('videos/<uuid:video_id>/transcript/', views.TranscriptDetailView.as_view(), name='transcript-detail'),
    path('videos/<uuid:video_id>/sections/', views.VideoSectionListView.as_view(), name='section-list'),
    path('videos/<uuid:video_id>/knowledge/', views.KnowledgePointsByVideoView.as_view(), name='knowledge-list'),
    path('videos/<uuid:video_id>/knowledge/grouped/', views.SectionsWithKnowledgeView.as_view(), name='knowledge-grouped'),
    path('videos/<uuid:video_id>/summary/', views.KnowledgeSummaryDetailView.as_view(), name='summary-detail'),
    path('videos/<uuid:video_id>/mindmap/', views.KnowledgeMindmapDetailView.as_view(), name='mindmap-detail'),
    path('videos/process/', views.VideoTaskTriggerView.as_view(), name='video-task-process'),

    # Chat (RAG)
    path('videos/<uuid:video_id>/chat/sessions/', views.ChatSessionListCreateView.as_view(), name='chat-session-list'),
    path('videos/<uuid:video_id>/chat/stream/', views.chat_stream_view, name='chat-stream'),
    path('videos/<uuid:video_id>/chat/ask/', views.chat_ask_view, name='chat-ask'),
    path('chat/sessions/<uuid:pk>/', views.ChatSessionDetailView.as_view(), name='chat-session-detail'),
    path('chat/sessions/<uuid:session_id>/messages/', views.ChatMessageListView.as_view(), name='chat-message-list'),

    # Agent Chat (LangGraph)
    path('videos/<uuid:video_id>/agent/stream/', views.agent_chat_stream_view, name='agent-stream'),

    # Course Agent Chat
    path('episodes/<uuid:episode_id>/agent/stream/', views.course_agent_stream_view, name='course-agent-stream'),

    # Sections
    path('sections/<uuid:section_id>/knowledge/', views.KnowledgePointsBySectionView.as_view(), name='section-knowledge'),

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
    path('tasks/<uuid:pk>/retry/', views.task_retry_view, name='task-retry'),

    # System Configuration
    path('config/', views.system_config_list, name='config-list'),
    path('config/update/', views.system_config_update, name='config-update'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
