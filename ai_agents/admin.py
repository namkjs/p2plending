from django.contrib import admin
from .models import AgentLog, Notification
from lending.models import LenderMatchResult


@admin.register(AgentLog)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "agent_type",
        "user",
        "status",
        "processing_time_ms",
        "created_at",
    ]
    list_filter = ["agent_type", "status", "created_at"]
    search_fields = ["user__username", "error_message"]
    readonly_fields = ["created_at", "completed_at", "input_data", "output_data"]

    fieldsets = (
        ("Thông tin", {"fields": ("agent_type", "user", "status")}),
        ("Dữ liệu", {"fields": ("input_data", "output_data", "error_message")}),
        ("Thời gian", {"fields": ("created_at", "completed_at", "processing_time_ms")}),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "notification_type", "title", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read", "created_at"]
    search_fields = ["user__username", "title", "message"]
    readonly_fields = ["created_at"]

    actions = ["mark_as_read"]

    @admin.action(description="Đánh dấu đã đọc")
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
        self.message_user(request, f"Đã đánh dấu {queryset.count()} thông báo")
