"""
Agent Lender Matcher: Kết nối người cho vay phù hợp
- Tìm người cho vay phù hợp với đơn vay
- Tính điểm matching
- Gửi thông báo cho lender
"""

import time
from typing import Any, Dict, List
from django.contrib.auth.models import User
from django.db.models import Q

from .base import BaseAgent


class LenderMatcherAgent(BaseAgent):
    """Agent kết nối người cho vay phù hợp"""

    agent_type = "LENDER_MATCHER"

    SYSTEM_PROMPT = """Bạn là chuyên gia kết nối đầu tư cho nền tảng P2P Lending.
Nhiệm vụ: Phân tích và đánh giá mức độ phù hợp giữa đơn vay và người cho vay.

Các yếu tố cần xem xét:
1. Số tiền vay vs ngân sách đầu tư của lender
2. Lãi suất mong muốn của cả 2 bên
3. Kỳ hạn vay vs preference của lender
4. Mức độ rủi ro của borrower vs risk tolerance của lender
5. Lịch sử đầu tư của lender

Trả về JSON với format:
{
    "match_score": <số từ 0-100>,
    "match_reasons": {
        "amount_fit": <số từ 0-100>,
        "interest_rate_fit": <số từ 0-100>,
        "duration_fit": <số từ 0-100>,
        "risk_fit": <số từ 0-100>
    },
    "recommendation": "lý do nên/không nên đầu tư",
    "potential_return": <số tiền lãi dự kiến>,
    "risk_assessment": "đánh giá rủi ro cho lender"
}"""

    def process(self, loan_request) -> Dict[str, Any]:
        """
        Tìm và matching người cho vay phù hợp

        Args:
            loan_request: LoanRequest object

        Returns:
            Dict với danh sách matches
        """
        start_time = time.time()

        input_data = {
            "loan_request_id": loan_request.id,
            "amount": float(loan_request.amount),
            "interest_rate": loan_request.interest_rate,
            "duration_months": loan_request.duration_months,
            "purpose": loan_request.purpose,
        }

        log = self._log_start(loan_request.borrower, input_data)

        try:
            # Find potential lenders
            potential_lenders = self._find_potential_lenders(loan_request)

            # Score each lender
            matches = []
            for lender_profile in potential_lenders:
                match_result = self._calculate_match(loan_request, lender_profile)
                if match_result["match_score"] >= 50:  # Minimum threshold
                    matches.append(
                        {
                            "lender_id": lender_profile.user.id,
                            "lender_username": lender_profile.user.username,
                            **match_result,
                        }
                    )

            # Sort by match score
            matches.sort(key=lambda x: x["match_score"], reverse=True)

            # Save matches to database
            self._save_matches(loan_request, matches[:10])  # Top 10

            # Notify top lenders
            self._notify_lenders(loan_request, matches[:5])  # Top 5

            result = {"matches": matches[:10], "total_found": len(matches)}
            self._log_success(log, result, start_time)

            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _find_potential_lenders(self, loan_request) -> List:
        """Tìm danh sách lender tiềm năng"""
        from lending.models import LenderProfile

        return (
            LenderProfile.objects.filter(
                is_active=True,
                min_amount__lte=loan_request.amount,
                max_amount__gte=loan_request.amount,
                preferred_duration_min__lte=loan_request.duration_months,
                preferred_duration_max__gte=loan_request.duration_months,
            )
            .exclude(user=loan_request.borrower)
            .select_related("user")
        )

    def _calculate_match(self, loan_request, lender_profile) -> Dict:
        """Tính điểm matching bằng AI"""
        from lending.models import BorrowerRiskProfile
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        # Get borrower risk profile
        borrower_risk = None
        try:
            borrower_risk = BorrowerRiskProfile.objects.get(user=loan_request.borrower)
        except BorrowerRiskProfile.DoesNotExist:
            pass

        match_data = {
            "loan_request": {
                "amount": float(loan_request.amount),
                "interest_rate": loan_request.interest_rate,
                "duration_months": loan_request.duration_months,
                "purpose": loan_request.purpose,
                "borrower_credit_score": (
                    borrower_risk.credit_score if borrower_risk else 500
                ),
                "borrower_risk_level": (
                    borrower_risk.risk_level if borrower_risk else "MEDIUM"
                ),
            },
            "lender_profile": {
                "min_amount": float(lender_profile.min_amount),
                "max_amount": float(lender_profile.max_amount),
                "min_interest_rate": lender_profile.min_interest_rate,
                "preferred_duration_min": lender_profile.preferred_duration_min,
                "preferred_duration_max": lender_profile.preferred_duration_max,
                "risk_tolerance": lender_profile.risk_tolerance,
                "total_invested": float(lender_profile.total_invested),
                "active_investments": lender_profile.active_investments,
            },
        }

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.SYSTEM_PROMPT),
                ("human", "Đánh giá mức độ phù hợp:\n{match_data}"),
            ]
        )

        chain = prompt | self._get_llm() | JsonOutputParser()
        result = chain.invoke({"match_data": str(match_data)})

        return result

    def _save_matches(self, loan_request, matches: List[Dict]):
        """Lưu kết quả matching vào database"""
        from ai_agents.models import LenderMatchResult
        from django.contrib.auth.models import User

        for match in matches:
            lender = User.objects.get(id=match["lender_id"])
            LenderMatchResult.objects.update_or_create(
                loan_request=loan_request,
                lender=lender,
                defaults={
                    "match_score": match["match_score"],
                    "match_reasons": match.get("match_reasons", {}),
                },
            )

    def _notify_lenders(self, loan_request, matches: List[Dict]):
        """Gửi thông báo cho các lender phù hợp"""
        from django.contrib.auth.models import User

        for match in matches:
            lender = User.objects.get(id=match["lender_id"])
            self._create_notification(
                lender,
                "MATCH_FOUND",
                "Cơ hội đầu tư mới!",
                f"Có đơn vay {loan_request.amount:,.0f} VNĐ phù hợp với bạn. "
                f"Điểm phù hợp: {match['match_score']}%. Lãi suất: {loan_request.interest_rate}%/năm.",
            )
