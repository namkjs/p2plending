from django.db import models
from django.contrib.auth.models import User

# Import model UserProfile nếu cần (thường dùng user là đủ)


class LoanRequest(models.Model):
    """Đơn xin vay tiền"""

    borrower = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="loan_requests"
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.FloatField(help_text="% Lãi suất mong muốn/năm")
    duration_months = models.IntegerField(help_text="Kỳ hạn (tháng)")
    purpose = models.TextField(help_text="Mục đích vay (AI sẽ đọc cái này)")

    STATUS_CHOICES = [
        ("PENDING", "Đang chờ duyệt"),
        ("APPROVED", "Đã duyệt sàn"),  # AI duyệt xong
        ("FUNDED", "Đã giải ngân"),
        ("REJECTED", "Bị từ chối"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Vay {self.amount} - {self.borrower.username}"


class LoanContract(models.Model):
    """Hợp đồng vay chính thức (Kết quả của Agent Contract Generator)"""

    loan_request = models.OneToOneField(LoanRequest, on_delete=models.CASCADE)
    lender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="investments"
    )

    # Nội dung hợp đồng do AI sinh ra
    contract_text = models.TextField(verbose_name="Nội dung hợp đồng")
    signed_date = models.DateTimeField(auto_now_add=True)

    # Trạng thái thanh toán
    is_active = models.BooleanField(default=True)
    is_disputed = models.BooleanField(default=False)  # Có đang tranh chấp không?


class RepaymentSchedule(models.Model):
    """Lịch trả nợ (Để Agent Payment Monitor theo dõi)"""

    contract = models.ForeignKey(
        LoanContract, on_delete=models.CASCADE, related_name="schedules"
    )
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=15, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    def __str__(self):
        return f"Kỳ hạn {self.due_date} - {self.amount_due}"


class Dispute(models.Model):
    """Tranh chấp (Để Agent Dispute Resolver xử lý)"""

    contract = models.ForeignKey(
        LoanContract, on_delete=models.CASCADE, related_name="disputes"
    )
    raised_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="raised_disputes"
    )

    DISPUTE_TYPE_CHOICES = [
        ("LATE_PAYMENT", "Chậm thanh toán"),
        ("WRONG_AMOUNT", "Sai số tiền"),
        ("CONTRACT_VIOLATION", "Vi phạm hợp đồng"),
        ("OTHER", "Khác"),
    ]
    dispute_type = models.CharField(max_length=30, choices=DISPUTE_TYPE_CHOICES)
    description = models.TextField(help_text="Mô tả chi tiết tranh chấp")

    STATUS_CHOICES = [
        ("OPEN", "Đang mở"),
        ("IN_REVIEW", "Đang xem xét"),
        ("RESOLVED", "Đã giải quyết"),
        ("ESCALATED", "Đã chuyển lên cấp cao"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="OPEN")

    # AI resolution
    ai_analysis = models.TextField(blank=True, null=True)
    ai_recommendation = models.TextField(blank=True, null=True)
    resolution_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Tranh chấp #{self.id} - {self.dispute_type}"


class LenderProfile(models.Model):
    """Hồ sơ người cho vay (Để Agent Lender Matcher sử dụng)"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="lender_profile"
    )

    # Preference cho việc đầu tư
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, default=1000000)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, default=100000000)
    min_interest_rate = models.FloatField(
        default=8.0, help_text="% Lãi suất tối thiểu mong muốn"
    )
    preferred_duration_min = models.IntegerField(
        default=1, help_text="Kỳ hạn tối thiểu (tháng)"
    )
    preferred_duration_max = models.IntegerField(
        default=24, help_text="Kỳ hạn tối đa (tháng)"
    )

    RISK_TOLERANCE_CHOICES = [
        ("LOW", "Thấp - Chỉ cho vay hồ sơ tốt"),
        ("MEDIUM", "Trung bình"),
        ("HIGH", "Cao - Chấp nhận rủi ro"),
    ]
    risk_tolerance = models.CharField(
        max_length=10, choices=RISK_TOLERANCE_CHOICES, default="MEDIUM"
    )

    # Statistics
    total_invested = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_returns = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    active_investments = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Lender: {self.user.username}"


class BorrowerRiskProfile(models.Model):
    """Hồ sơ rủi ro người vay (Kết quả từ Agent Borrower Profiler)"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="risk_profile"
    )

    # Credit Score do AI tính toán
    credit_score = models.IntegerField(default=0, help_text="Điểm tín dụng (0-1000)")

    RISK_LEVEL_CHOICES = [
        ("VERY_LOW", "Rất thấp"),
        ("LOW", "Thấp"),
        ("MEDIUM", "Trung bình"),
        ("HIGH", "Cao"),
        ("VERY_HIGH", "Rất cao"),
    ]
    risk_level = models.CharField(
        max_length=15, choices=RISK_LEVEL_CHOICES, default="MEDIUM"
    )

    # Các yếu tố AI phân tích
    income_stability = models.FloatField(
        default=0, help_text="Độ ổn định thu nhập (0-100)"
    )
    debt_to_income_ratio = models.FloatField(default=0, help_text="Tỷ lệ nợ/thu nhập")
    payment_history_score = models.FloatField(
        default=0, help_text="Điểm lịch sử thanh toán (0-100)"
    )

    # AI analysis
    ai_analysis = models.JSONField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Risk Profile: {self.user.username} - Score: {self.credit_score}"


class LenderMatchResult(models.Model):
    """Kết quả matching giữa khoản vay và người cho vay"""

    loan_request = models.ForeignKey(
        LoanRequest, on_delete=models.CASCADE, related_name="match_results"
    )
    lender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="loan_matches"
    )
    match_score = models.FloatField(default=0, help_text="Điểm phù hợp (0-100)")
    match_reasons = models.JSONField(default=list, help_text="Lý do match")

    # Status
    is_notified = models.BooleanField(default=False)
    is_viewed = models.BooleanField(default=False)
    is_interested = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["loan_request", "lender"]
        ordering = ["-match_score"]

    def __str__(self):
        return f"Match: Loan #{self.loan_request.id} - {self.lender.username} ({self.match_score}%)"
