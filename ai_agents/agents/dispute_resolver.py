"""
Agent Dispute Resolver: Xử lý tranh chấp, đề xuất giải pháp
- Phân tích tranh chấp
- Đề xuất giải pháp công bằng
- Hỗ trợ hòa giải
"""

import time
from typing import Any, Dict
from django.utils import timezone

from .base import BaseAgent


class DisputeResolverAgent(BaseAgent):
    """Agent xử lý tranh chấp và đề xuất giải pháp"""

    agent_type = "DISPUTE_RESOLVER"

    SYSTEM_PROMPT = """Bạn là chuyên gia hòa giải tranh chấp cho nền tảng P2P Lending.
Nhiệm vụ: Phân tích tranh chấp và đề xuất giải pháp công bằng cho cả 2 bên.

Nguyên tắc:
1. Công bằng - Xem xét quyền lợi cả 2 bên
2. Dựa trên hợp đồng - Căn cứ điều khoản đã ký
3. Thực tế - Đề xuất giải pháp khả thi
4. Bảo vệ nền tảng - Giữ uy tín hệ thống

Các loại tranh chấp:
- LATE_PAYMENT: Chậm thanh toán
- WRONG_AMOUNT: Sai số tiền
- CONTRACT_VIOLATION: Vi phạm hợp đồng
- OTHER: Khác

Trả về JSON với format:
{
    "analysis": {
        "summary": "tóm tắt tranh chấp",
        "borrower_position": "quan điểm người vay",
        "lender_position": "quan điểm người cho vay",
        "contract_terms": "điều khoản liên quan trong hợp đồng",
        "facts": ["sự kiện 1", "sự kiện 2"]
    },
    "assessment": {
        "fault_analysis": "phân tích lỗi của các bên",
        "borrower_fault_percent": <% lỗi người vay>,
        "lender_fault_percent": <% lỗi người cho vay>,
        "platform_fault_percent": <% lỗi nền tảng nếu có>
    },
    "recommendation": {
        "primary_solution": "giải pháp chính",
        "alternative_solutions": ["giải pháp thay thế 1", "giải pháp thay thế 2"],
        "compensation": {
            "to_borrower": <số tiền bồi thường cho người vay nếu có>,
            "to_lender": <số tiền bồi thường cho người cho vay nếu có>
        },
        "action_items": [
            {"party": "borrower|lender|platform", "action": "hành động cần thực hiện"}
        ],
        "timeline_days": <số ngày đề xuất giải quyết>
    },
    "escalation_needed": <true|false>,
    "escalation_reason": "lý do cần chuyển lên cấp cao nếu có"
}"""

    def process(self, dispute) -> Dict[str, Any]:
        """
        Xử lý tranh chấp

        Args:
            dispute: Dispute object

        Returns:
            Dict với phân tích và đề xuất
        """
        start_time = time.time()

        input_data = self._gather_dispute_data(dispute)
        log = self._log_start(dispute.raised_by, input_data)

        try:
            # Analyze dispute
            analysis = self._analyze_dispute(input_data)

            # Update dispute record
            self._update_dispute(dispute, analysis)

            # Notify parties
            self._notify_parties(dispute, analysis)

            result = {"dispute_id": dispute.id, "analysis": analysis}

            self._log_success(log, result, start_time)
            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _gather_dispute_data(self, dispute) -> Dict:
        """Thu thập dữ liệu tranh chấp"""
        contract = dispute.contract
        loan_request = contract.loan_request
        borrower = loan_request.borrower
        lender = contract.lender

        # Get payment history
        from lending.models import RepaymentSchedule

        schedules = RepaymentSchedule.objects.filter(contract=contract)

        payment_history = []
        for s in schedules:
            payment_history.append(
                {
                    "due_date": str(s.due_date),
                    "amount": float(s.amount_due),
                    "is_paid": s.is_paid,
                    "paid_date": str(s.paid_date) if s.paid_date else None,
                }
            )

        return {
            "dispute_id": dispute.id,
            "dispute_type": dispute.dispute_type,
            "description": dispute.description,
            "raised_by": dispute.raised_by.username,
            "created_at": str(dispute.created_at),
            "contract": {
                "id": contract.id,
                "contract_text": contract.contract_text[:1000],  # Truncate for context
                "signed_date": str(contract.signed_date),
                "is_disputed": contract.is_disputed,
            },
            "loan_details": {
                "amount": float(loan_request.amount),
                "interest_rate": loan_request.interest_rate,
                "duration_months": loan_request.duration_months,
                "purpose": loan_request.purpose,
            },
            "borrower": {
                "username": borrower.username,
                "profile": self._get_user_profile(borrower),
            },
            "lender": {
                "username": lender.username,
                "profile": self._get_user_profile(lender),
            },
            "payment_history": payment_history,
        }

    def _get_user_profile(self, user) -> Dict:
        """Lấy thông tin profile user"""
        if hasattr(user, "profile"):
            profile = user.profile
            return {
                "full_name": profile.full_name,
                "kyc_status": profile.kyc_status,
            }
        return {}

    def _analyze_dispute(self, dispute_data: Dict) -> Dict:
        """Phân tích tranh chấp bằng AI"""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.SYSTEM_PROMPT),
                (
                    "human",
                    "Phân tích và đề xuất giải pháp cho tranh chấp sau:\n{dispute_data}",
                ),
            ]
        )

        chain = prompt | self._get_llm() | JsonOutputParser()
        result = chain.invoke({"dispute_data": str(dispute_data)})

        return result

    def _update_dispute(self, dispute, analysis: Dict):
        """Cập nhật tranh chấp trong database"""
        dispute.ai_analysis = str(analysis.get("analysis", {}))
        dispute.ai_recommendation = str(analysis.get("recommendation", {}))

        if analysis.get("escalation_needed", False):
            dispute.status = "ESCALATED"
        else:
            dispute.status = "IN_REVIEW"

        dispute.save()

        # Mark contract as disputed
        dispute.contract.is_disputed = True
        dispute.contract.save()

    def _notify_parties(self, dispute, analysis: Dict):
        """Thông báo cho các bên liên quan"""
        contract = dispute.contract
        borrower = contract.loan_request.borrower
        lender = contract.lender

        recommendation = analysis.get("recommendation", {})
        primary_solution = recommendation.get("primary_solution", "Đang xem xét")

        # Notify borrower
        self._create_notification(
            borrower,
            "DISPUTE_UPDATE",
            f"Tranh chấp #{dispute.id} đã được phân tích",
            f"Hệ thống đã phân tích tranh chấp của bạn. "
            f"Đề xuất: {primary_solution[:200]}...",
        )

        # Notify lender
        self._create_notification(
            lender,
            "DISPUTE_UPDATE",
            f"Tranh chấp #{dispute.id} đã được phân tích",
            f"Hệ thống đã phân tích tranh chấp. "
            f"Đề xuất: {primary_solution[:200]}...",
        )

    def resolve_dispute(self, dispute, resolution_notes: str) -> Dict[str, Any]:
        """
        Đánh dấu tranh chấp đã giải quyết

        Args:
            dispute: Dispute object
            resolution_notes: Ghi chú giải quyết

        Returns:
            Dict với kết quả
        """
        dispute.status = "RESOLVED"
        dispute.resolution_notes = resolution_notes
        dispute.resolved_at = timezone.now()
        dispute.save()

        # Update contract
        dispute.contract.is_disputed = False
        dispute.contract.save()

        # Notify parties
        borrower = dispute.contract.loan_request.borrower
        lender = dispute.contract.lender

        self._create_notification(
            borrower,
            "DISPUTE_UPDATE",
            f"Tranh chấp #{dispute.id} đã được giải quyết",
            f"Tranh chấp đã được giải quyết. Ghi chú: {resolution_notes[:200]}...",
        )

        self._create_notification(
            lender,
            "DISPUTE_UPDATE",
            f"Tranh chấp #{dispute.id} đã được giải quyết",
            f"Tranh chấp đã được giải quyết. Ghi chú: {resolution_notes[:200]}...",
        )

        return {"success": True, "dispute_id": dispute.id, "status": "RESOLVED"}
