"""
Agent Borrower Profiler: Đánh giá hồ sơ người vay
- Phân tích thông tin KYC
- Tính toán credit score
- Đánh giá mức độ rủi ro
"""

import time
from typing import Any, Dict
from django.contrib.auth.models import User

from .base import BaseAgent


class BorrowerProfilerAgent(BaseAgent):
    """Agent đánh giá hồ sơ người vay"""

    agent_type = "BORROWER_PROFILER"

    SYSTEM_PROMPT = """Bạn là chuyên gia đánh giá tín dụng cho nền tảng P2P Lending.
Nhiệm vụ: Phân tích hồ sơ người vay và đưa ra đánh giá rủi ro.

Các yếu tố cần xem xét:
1. Thông tin cá nhân (tuổi, nghề nghiệp, địa chỉ)
2. Thu nhập và ổn định công việc
3. Lịch sử vay trả (nếu có)
4. Mục đích vay
5. Tỷ lệ nợ/thu nhập

Trả về JSON với format:
{
    "credit_score": <số từ 0-1000>,
    "risk_level": "<VERY_LOW|LOW|MEDIUM|HIGH|VERY_HIGH>",
    "income_stability": <số từ 0-100>,
    "debt_to_income_ratio": <số thập phân>,
    "payment_history_score": <số từ 0-100>,
    "analysis": {
        "strengths": ["điểm mạnh 1", "điểm mạnh 2"],
        "weaknesses": ["điểm yếu 1", "điểm yếu 2"],
        "recommendation": "khuyến nghị cho vay hay không",
        "max_loan_amount": <số tiền tối đa nên cho vay>,
        "suggested_interest_rate": <lãi suất đề xuất %>
    }
}"""

    def process(self, user: User, loan_request=None) -> Dict[str, Any]:
        """
        Đánh giá hồ sơ người vay

        Args:
            user: Django User object
            loan_request: LoanRequest object (optional)

        Returns:
            Dict với kết quả đánh giá
        """
        start_time = time.time()

        # Gather user data
        input_data = self._gather_user_data(user, loan_request)
        log = self._log_start(user, input_data)

        try:
            # Call LLM for analysis
            result = self._analyze_profile(input_data)

            # Update risk profile in database
            self._update_risk_profile(user, result)

            # Log success
            self._log_success(log, result, start_time)

            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _gather_user_data(self, user: User, loan_request=None) -> Dict:
        """Thu thập dữ liệu người vay"""
        data = {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
        }

        # Get profile data
        if hasattr(user, "profile"):
            profile = user.profile
            data.update(
                {
                    "full_name": profile.full_name,
                    "id_card_number": (
                        profile.id_card_number[:4] + "****"
                        if profile.id_card_number
                        else ""
                    ),
                    "address": profile.address,
                    "kyc_status": profile.kyc_status,
                    "balance": float(profile.balance),
                }
            )

        # Get KYC documents data
        kyc_docs = user.kyc_docs.all() if hasattr(user, "kyc_docs") else []
        data["kyc_documents"] = [
            {"doc_type": doc.doc_type, "ai_extracted_data": doc.ai_extracted_data}
            for doc in kyc_docs
        ]

        # Get loan history
        past_loans = (
            user.loan_requests.filter(status="FUNDED").count()
            if hasattr(user, "loan_requests")
            else 0
        )
        data["loan_history"] = {
            "total_past_loans": past_loans,
            "completed_loans": 0,  # Will be calculated from contracts
            "default_count": 0,
        }

        # Current loan request
        if loan_request:
            data["current_request"] = {
                "amount": float(loan_request.amount),
                "interest_rate": loan_request.interest_rate,
                "duration_months": loan_request.duration_months,
                "purpose": loan_request.purpose,
            }

        return data

    def _analyze_profile(self, input_data: Dict) -> Dict:
        """Phân tích hồ sơ bằng AI"""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.SYSTEM_PROMPT),
                ("human", "Phân tích hồ sơ người vay sau:\n{user_data}"),
            ]
        )

        chain = prompt | self._get_llm() | JsonOutputParser()

        result = chain.invoke({"user_data": str(input_data)})
        return result

    def _update_risk_profile(self, user: User, analysis: Dict):
        """Cập nhật risk profile trong database"""
        from lending.models import BorrowerRiskProfile

        profile, created = BorrowerRiskProfile.objects.get_or_create(user=user)

        profile.credit_score = analysis.get("credit_score", 500)
        profile.risk_level = analysis.get("risk_level", "MEDIUM")
        profile.income_stability = analysis.get("income_stability", 50)
        profile.debt_to_income_ratio = analysis.get("debt_to_income_ratio", 0)
        profile.payment_history_score = analysis.get("payment_history_score", 50)
        profile.ai_analysis = analysis.get("analysis", {})
        profile.save()

        # Create notification
        self._create_notification(
            user,
            "KYC_STATUS",
            "Hồ sơ đã được đánh giá",
            f"Điểm tín dụng của bạn: {profile.credit_score}/1000. Mức rủi ro: {profile.risk_level}",
        )
