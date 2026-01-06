from django.contrib import admin
from .models import (
    LoanRequest,
    LoanContract,
    RepaymentSchedule,
    Dispute,
    LenderProfile,
    BorrowerRiskProfile,
    LenderMatchResult,
)


@admin.register(LoanRequest)
class LoanRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "borrower",
        "amount",
        "interest_rate",
        "duration_months",
        "status",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["borrower__username", "purpose"]
    readonly_fields = ["created_at"]

    actions = ["approve_loans", "reject_loans"]

    @admin.action(description="Duyệt đơn vay đã chọn")
    def approve_loans(self, request, queryset):
        from ai_agents.agents import LenderMatcherAgent

        agent = LenderMatcherAgent()
        for loan in queryset.filter(status="PENDING"):
            loan.status = "APPROVED"
            loan.save()
            agent.process(loan)
        self.message_user(request, f"Đã duyệt {queryset.count()} đơn vay")

    @admin.action(description="Từ chối đơn vay đã chọn")
    def reject_loans(self, request, queryset):
        queryset.update(status="REJECTED")
        self.message_user(request, f"Đã từ chối {queryset.count()} đơn vay")


@admin.register(LoanContract)
class LoanContractAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "get_borrower",
        "lender",
        "get_amount",
        "is_active",
        "is_disputed",
        "signed_date",
    ]
    list_filter = ["is_active", "is_disputed", "signed_date"]
    search_fields = ["loan_request__borrower__username", "lender__username"]
    readonly_fields = ["signed_date"]

    @admin.display(description="Người vay")
    def get_borrower(self, obj):
        return obj.loan_request.borrower.username

    @admin.display(description="Số tiền")
    def get_amount(self, obj):
        return f"{obj.loan_request.amount:,.0f} VNĐ"


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "contract",
        "due_date",
        "amount_due",
        "is_paid",
        "paid_date",
        "reminder_sent",
    ]
    list_filter = ["is_paid", "reminder_sent", "due_date"]
    search_fields = ["contract__loan_request__borrower__username"]

    actions = ["mark_as_paid", "send_reminders"]

    @admin.action(description="Đánh dấu đã thanh toán")
    def mark_as_paid(self, request, queryset):
        from django.utils import timezone

        queryset.update(is_paid=True, paid_date=timezone.now().date())
        self.message_user(request, f"Đã cập nhật {queryset.count()} kỳ hạn")

    @admin.action(description="Gửi nhắc nhở")
    def send_reminders(self, request, queryset):
        from ai_agents.agents import PaymentMonitorAgent

        agent = PaymentMonitorAgent()
        agent.process()
        self.message_user(request, "Đã gửi nhắc nhở")


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "contract",
        "raised_by",
        "dispute_type",
        "status",
        "created_at",
    ]
    list_filter = ["status", "dispute_type", "created_at"]
    search_fields = ["contract__loan_request__borrower__username", "description"]
    readonly_fields = ["created_at", "resolved_at", "ai_analysis", "ai_recommendation"]

    actions = ["resolve_disputes", "run_ai_analysis"]

    @admin.action(description="Đánh dấu đã giải quyết")
    def resolve_disputes(self, request, queryset):
        from django.utils import timezone

        queryset.update(status="RESOLVED", resolved_at=timezone.now())
        self.message_user(request, f"Đã giải quyết {queryset.count()} tranh chấp")

    @admin.action(description="Chạy AI phân tích")
    def run_ai_analysis(self, request, queryset):
        from ai_agents.agents import DisputeResolverAgent

        agent = DisputeResolverAgent()
        for dispute in queryset:
            agent.process(dispute)
        self.message_user(request, f"Đã phân tích {queryset.count()} tranh chấp")


@admin.register(LenderProfile)
class LenderProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "min_amount",
        "max_amount",
        "min_interest_rate",
        "risk_tolerance",
        "is_active",
        "total_invested",
    ]
    list_filter = ["is_active", "risk_tolerance"]
    search_fields = ["user__username"]


@admin.register(BorrowerRiskProfile)
class BorrowerRiskProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "credit_score",
        "risk_level",
        "income_stability",
        "debt_to_income_ratio",
        "last_updated",
    ]
    list_filter = ["risk_level"]
    search_fields = ["user__username"]
    readonly_fields = ["last_updated", "ai_analysis"]


@admin.register(LenderMatchResult)
class LenderMatchResultAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "loan_request",
        "lender",
        "match_score",
        "is_notified",
        "is_viewed",
        "is_interested",
        "created_at",
    ]
    list_filter = ["is_notified", "is_viewed", "is_interested", "created_at"]
    search_fields = ["loan_request__borrower__username", "lender__username"]
    readonly_fields = ["created_at", "match_reasons"]
