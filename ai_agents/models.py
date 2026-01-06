from django.db import models
from django.contrib.auth.models import User


class AgentLog(models.Model):
    """Log hoạt động của các AI Agent"""

    AGENT_CHOICES = [
        ("BORROWER_PROFILER", "Agent Borrower Profiler"),
        ("LENDER_MATCHER", "Agent Lender Matcher"),
        ("CONTRACT_GENERATOR", "Agent Contract Generator"),
        ("PAYMENT_MONITOR", "Agent Payment Monitor"),
        ("DISPUTE_RESOLVER", "Agent Dispute Resolver"),
    ]
    agent_type = models.CharField(max_length=30, choices=AGENT_CHOICES)

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    # Input/Output của Agent
    input_data = models.JSONField(help_text="Dữ liệu đầu vào")
    output_data = models.JSONField(null=True, blank=True, help_text="Kết quả xử lý")

    STATUS_CHOICES = [
        ("PENDING", "Đang xử lý"),
        ("SUCCESS", "Thành công"),
        ("FAILED", "Thất bại"),
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="PENDING")
    error_message = models.TextField(blank=True, null=True)

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.agent_type} - {self.status} - {self.created_at}"


class Notification(models.Model):
    """Thông báo cho user (Được tạo bởi các Agent)"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )

    NOTIFICATION_TYPE_CHOICES = [
        ("PAYMENT_REMINDER", "Nhắc thanh toán"),
        ("LOAN_APPROVED", "Đơn vay được duyệt"),
        ("LOAN_REJECTED", "Đơn vay bị từ chối"),
        ("LOAN_FUNDED", "Đơn vay được giải ngân"),
        ("MATCH_FOUND", "Tìm được người cho vay"),
        ("LOAN_MATCH", "Khoản vay phù hợp"),
        ("CONTRACT_READY", "Hợp đồng đã sẵn sàng"),
        ("DISPUTE_UPDATE", "Cập nhật tranh chấp"),
        ("KYC_STATUS", "Trạng thái KYC"),
        ("SYSTEM", "Thông báo hệ thống"),
    ]
    notification_type = models.CharField(
        max_length=30, choices=NOTIFICATION_TYPE_CHOICES
    )

    title = models.CharField(max_length=200)
    message = models.TextField()

    # Related loan (optional)
    related_loan = models.ForeignKey(
        "lending.LoanRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type} - {self.user.username}"
