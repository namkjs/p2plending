"""
Agent Lender Matcher: Kết nối người cho vay phù hợp
- Sử dụng SQL tools để search khoản vay
- Tìm người cho vay phù hợp với đơn vay
- Tính điểm matching
- Gửi thông báo cho lender
"""

import time
import json
from typing import Any, Dict, List
from django.contrib.auth.models import User
from django.db.models import Q

from .base import BaseAgent
from ai_agents.tools.sql_tools import (
    search_loans_by_interest_rate,
    search_loans_by_amount,
    search_loans_by_duration,
    search_loans_advanced,
    get_loan_detail,
    get_lender_preferences,
    get_user_balance,
    find_matching_lenders_for_loan,
    get_loan_statistics,
)


class LenderMatcherAgent(BaseAgent):
    """Agent kết nối người cho vay phù hợp với SQL tools"""

    agent_type = "LENDER_MATCHER"

    system_prompt = """Bạn là Lender Matcher Agent cho nền tảng P2P Lending.

Nhiệm vụ của bạn:
1. Tìm kiếm các khoản vay phù hợp với tiêu chí của người cho vay
2. Tìm kiếm người cho vay phù hợp cho một khoản vay cụ thể
3. Đánh giá mức độ phù hợp và đưa ra khuyến nghị

Các yếu tố cần xem xét khi matching:
1. Số tiền vay vs ngân sách đầu tư của lender
2. Lãi suất mong muốn của cả 2 bên  
3. Kỳ hạn vay vs preference của lender
4. Mức độ rủi ro của borrower vs risk tolerance của lender

Bạn có thể sử dụng các công cụ sau:
- search_loans_by_interest_rate: Tìm khoản vay theo lãi suất
- search_loans_by_amount: Tìm khoản vay theo số tiền
- search_loans_by_duration: Tìm khoản vay theo kỳ hạn
- search_loans_advanced: Tìm kiếm nâng cao với nhiều tiêu chí
- get_loan_detail: Xem chi tiết một khoản vay
- get_lender_preferences: Xem tiêu chí đầu tư của người cho vay
- get_user_balance: Kiểm tra số dư ví
- find_matching_lenders_for_loan: Tìm người cho vay phù hợp cho khoản vay
- get_loan_statistics: Xem thống kê chung

Hãy sử dụng các công cụ này để trả lời câu hỏi của người dùng một cách chính xác."""

    tools = [
        search_loans_by_interest_rate,
        search_loans_by_amount,
        search_loans_by_duration,
        search_loans_advanced,
        get_loan_detail,
        get_lender_preferences,
        get_user_balance,
        find_matching_lenders_for_loan,
        get_loan_statistics,
    ]

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
            # Sử dụng tool để tìm lender phù hợp
            matching_result = find_matching_lenders_for_loan.invoke(loan_request.id)

            # Find potential lenders bằng query truyền thống
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

            result = {
                "matches": matches[:10],
                "total_found": len(matches),
                "tool_result": matching_result,
            }
            self._log_success(log, result, start_time)

            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def search_loans_for_lender(self, user_id: int, query: str) -> Dict[str, Any]:
        """
        Tìm kiếm khoản vay cho người cho vay dựa trên câu hỏi tự nhiên

        Args:
            user_id: ID của lender
            query: Câu hỏi tìm kiếm (VD: "Tìm khoản vay lãi suất 10-15%")

        Returns:
            Kết quả tìm kiếm
        """
        # Sử dụng agent với tools
        input_text = f"[user_id={user_id}] {query}"
        result = self.invoke(input_text)
        return {"success": True, "response": result}

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
        """Tính điểm matching"""
        from lending.models import BorrowerRiskProfile

        scores = {
            "amount_fit": 100,
            "interest_rate_fit": 100,
            "duration_fit": 100,
            "risk_fit": 70,  # Default
        }

        # Interest rate check
        if loan_request.interest_rate < lender_profile.min_interest_rate:
            diff = lender_profile.min_interest_rate - loan_request.interest_rate
            scores["interest_rate_fit"] = max(0, 100 - diff * 10)

        # Risk check
        try:
            risk_profile = BorrowerRiskProfile.objects.get(user=loan_request.borrower)
            risk_level = risk_profile.risk_level

            if lender_profile.risk_tolerance == "LOW":
                if risk_level in ["HIGH", "VERY_HIGH"]:
                    scores["risk_fit"] = 30
                elif risk_level == "MEDIUM":
                    scores["risk_fit"] = 60
                else:
                    scores["risk_fit"] = 100
            elif lender_profile.risk_tolerance == "MEDIUM":
                if risk_level in ["VERY_HIGH"]:
                    scores["risk_fit"] = 40
                else:
                    scores["risk_fit"] = 85
            else:  # HIGH tolerance
                scores["risk_fit"] = 100
        except BorrowerRiskProfile.DoesNotExist:
            pass

        # Calculate overall score
        weights = {
            "amount_fit": 0.25,
            "interest_rate_fit": 0.30,
            "duration_fit": 0.20,
            "risk_fit": 0.25,
        }

        match_score = sum(scores[k] * weights[k] for k in weights)

        # Calculate potential return
        principal = float(loan_request.amount)
        rate = loan_request.interest_rate / 100
        months = loan_request.duration_months
        potential_return = principal * rate * months / 12

        return {
            "match_score": round(match_score, 1),
            "match_reasons": scores,
            "potential_return": round(potential_return, 0),
            "risk_assessment": self._get_risk_assessment(scores["risk_fit"]),
        }

    def _get_risk_assessment(self, risk_score: float) -> str:
        """Đánh giá rủi ro"""
        if risk_score >= 80:
            return "Rủi ro thấp - Phù hợp đầu tư"
        elif risk_score >= 60:
            return "Rủi ro trung bình - Cân nhắc kỹ"
        elif risk_score >= 40:
            return "Rủi ro cao - Chỉ dành cho nhà đầu tư chấp nhận rủi ro"
        else:
            return "Rủi ro rất cao - Không khuyến nghị"

    def _save_matches(self, loan_request, matches: List[Dict]):
        """Lưu kết quả matching"""
        from lending.models import LenderMatchResult

        # Clear old matches
        LenderMatchResult.objects.filter(loan_request=loan_request).delete()

        for match in matches:
            LenderMatchResult.objects.create(
                loan_request=loan_request,
                lender_id=match["lender_id"],
                match_score=match["match_score"],
                match_reasons=match["match_reasons"],
                is_notified=False,
            )

    def _notify_lenders(self, loan_request, matches: List[Dict]):
        """Gửi thông báo cho lenders"""
        for match in matches:
            user = User.objects.get(id=match["lender_id"])
            self._create_notification(
                user=user,
                notification_type="LOAN_MATCH",
                title="Có khoản vay phù hợp mới!",
                message=f"""Khoản vay {loan_request.amount:,.0f} VNĐ với lãi suất {loan_request.interest_rate}%/năm
Kỳ hạn: {loan_request.duration_months} tháng
Độ phù hợp: {match['match_score']}%
Lợi nhuận dự kiến: {match['potential_return']:,.0f} VNĐ""",
                related_loan=loan_request,
            )

            # Update notification status
            from lending.models import LenderMatchResult

            LenderMatchResult.objects.filter(
                loan_request=loan_request, lender_id=match["lender_id"]
            ).update(is_notified=True)
