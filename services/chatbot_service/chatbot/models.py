from django.db import models


class BehaviorEvent(models.Model):
    EVENT_CHATBOT_ASK = "chatbot_ask"
    EVENT_CHOICES = [
        (EVENT_CHATBOT_ASK, "Chatbot ask"),
    ]

    user_ref = models.CharField(max_length=120, db_index=True)
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    category_slug = models.CharField(max_length=120, blank=True)
    product_id = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_ref} | {self.event_type}"
