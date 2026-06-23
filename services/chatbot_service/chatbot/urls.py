from django.urls import path

from .views import chat_reply_view, ingest_behavior_event_view

urlpatterns = [
    path("api/chat/reply/", chat_reply_view, name="chat_reply"),
    path("api/chat/ingest-behavior/", ingest_behavior_event_view, name="chat_ingest_behavior"),
]
