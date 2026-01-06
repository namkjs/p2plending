"""
Agent Borrower Profiler: Đánh giá hồ sơ người vay với OCR
- Sử dụng Mistral OCR để đọc CCCD
- Xác thực thông tin KYC
- Đánh giá rủi ro người vay
"""

import time
import json
from typing import Any, Dict, Optional
from django.contrib.auth.models import User

from .base import BaseAgent
from ai_agents.tools.ocr_tools import (
    ocr_id_card_front,
    ocr_id_card_back,
    verify_id_card_info,
    save_kyc_verification_result,
)
from ai_agents.tools.sql_tools import (
    get_user_kyc_status,
    get_user_balance,
)


class BorrowerProfilerAgent(BaseAgent):
    """Agent đánh giá hồ sơ người vay với OCR tools"""

    agent_type = "BORROWER_PROFILER"

    system_prompt = """Bạn là Borrower Profiler Agent cho nền tảng P2P Lending.

Nhiệm vụ của bạn:
1. Xác thực danh tính người vay qua CCCD
2. OCR thông tin từ ảnh CCCD sử dụng Mistral Vision
3. So sánh thông tin OCR với thông tin người dùng nhập
4. Đánh giá mức độ rủi ro của người vay
5. Lưu kết quả xác minh vào database

Quy trình KYC:
1. Nhận ảnh CCCD mặt trước và mặt sau
2. OCR để trích xuất thông tin
3. So sánh với thông tin người dùng đã nhập
4. Nếu độ khớp >= 70%: Xác thực thành công
5. Nếu độ khớp < 70%: Từ chối và yêu cầu kiểm tra lại

Bạn có thể sử dụng các công cụ sau:
- ocr_id_card_front: OCR mặt trước CCCD
- ocr_id_card_back: OCR mặt sau CCCD
- verify_id_card_info: So sánh thông tin
- save_kyc_verification_result: Lưu kết quả xác minh
- get_user_kyc_status: Kiểm tra trạng thái KYC

Hãy thực hiện xác minh cẩn thận và chính xác."""

    tools = [
        ocr_id_card_front,
        ocr_id_card_back,
        verify_id_card_info,
        save_kyc_verification_result,
        get_user_kyc_status,
        get_user_balance,
    ]

    def process(self, user, loan_request=None) -> Dict[str, Any]:
        """
        Đánh giá hồ sơ người vay

        Args:
            user: User object
            loan_request: Optional LoanRequest object

        Returns:
            Dict với kết quả đánh giá
        """
        start_time = time.time()

        input_data = {
            "user_id": user.id,
            "username": user.username,
            "loan_request_id": loan_request.id if loan_request else None,
        }

        log = self._log_start(user, input_data)

        try:
            # Lấy profile và KYC docs
            profile = getattr(user, "profile", None)
            if not profile:
                raise ValueError("User chưa có profile")

            # Kiểm tra KYC documents
            from user.models import KYCDocument

            kyc_docs = KYCDocument.objects.filter(user=user)

            if not kyc_docs.exists():
                raise ValueError("Chưa upload tài liệu KYC")

            # OCR và xác minh nếu chưa verified
            if profile.kyc_status != "VERIFIED":
                ocr_result = self._perform_ocr_verification(user, profile, kyc_docs)
                if not ocr_result["success"]:
                    raise ValueError(ocr_result.get("error", "OCR verification failed"))

            # Đánh giá rủi ro
            risk_assessment = self._assess_risk(user, profile, loan_request)

            # Cập nhật loan status nếu có
            if loan_request and profile.kyc_status == "VERIFIED":
                loan_request.status = "APPROVED"
                loan_request.save()

            result = {
                "kyc_status": profile.kyc_status,
                "ocr_verified": profile.ocr_verified,
                "ocr_match_score": profile.ocr_match_score,
                "risk_assessment": risk_assessment,
            }

            self._log_success(log, result, start_time)

            # Notify user
            self._notify_kyc_result(user, profile)

            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _perform_ocr_verification(self, user, profile, kyc_docs) -> Dict:
        """Thực hiện OCR và xác minh"""

        # Tìm ảnh CCCD mặt trước
        front_doc = kyc_docs.filter(doc_type="ID_CARD_FRONT").first()
        back_doc = kyc_docs.filter(doc_type="ID_CARD_BACK").first()

        if not front_doc:
            return {"success": False, "error": "Chưa upload CCCD mặt trước"}

        # OCR mặt trước - gọi trực tiếp hàm thay vì invoke
        front_ocr_result = ocr_id_card_front.func(image_path=front_doc.image.path)

        try:
            front_ocr = json.loads(front_ocr_result)
        except:
            front_ocr = {"success": False, "raw_text": front_ocr_result}

        if not front_ocr.get("success"):
            # Fallback: lưu raw text và tiếp tục
            front_ocr = {"success": True, "data": {"raw_text": front_ocr_result}}

        # Cập nhật OCR status cho document
        front_doc.ocr_status = "COMPLETED" if front_ocr.get("success") else "FAILED"
        front_doc.ocr_data = front_ocr.get("data", {})
        front_doc.save()

        # OCR mặt sau (optional)
        if back_doc:
            back_ocr_result = ocr_id_card_back.func(image_path=back_doc.image.path)
            try:
                back_ocr = json.loads(back_ocr_result)
                back_doc.ocr_status = (
                    "COMPLETED" if back_ocr.get("success") else "FAILED"
                )
                back_doc.ocr_data = back_ocr.get("data", {})
                back_doc.save()
            except:
                pass

        # Chuẩn bị dữ liệu để verify
        user_input = {
            "full_name": profile.full_name,
            "id_number": profile.id_card_number,
            "date_of_birth": (
                str(profile.date_of_birth) if profile.date_of_birth else ""
            ),
            "gender": profile.gender,
            "hometown": profile.hometown,
            "address": profile.address,
        }

        ocr_data = front_ocr.get("data", {})

        # Verify - gọi trực tiếp hàm thay vì invoke
        verify_result = verify_id_card_info.func(
            user_input=json.dumps(user_input, ensure_ascii=False),
            ocr_data=json.dumps(ocr_data, ensure_ascii=False),
        )

        # Save result - gọi trực tiếp hàm thay vì invoke
        save_result = save_kyc_verification_result.func(
            user_id=user.id, verification_result=verify_result
        )

        # Refresh profile
        profile.refresh_from_db()

        return {
            "success": profile.ocr_verified,
            "match_score": profile.ocr_match_score,
            "message": save_result,
        }

    def _assess_risk(self, user, profile, loan_request=None) -> Dict:
        """Đánh giá rủi ro người vay"""
        from lending.models import BorrowerRiskProfile, LoanContract

        # Get or create risk profile
        risk_profile, created = BorrowerRiskProfile.objects.get_or_create(
            user=user,
            defaults={
                "credit_score": 500,
                "risk_level": "MEDIUM",
            },
        )

        # Các yếu tố đánh giá
        factors = {
            "kyc_verified": 0,
            "income_stability": 0,
            "loan_history": 0,
            "debt_ratio": 0,
        }

        # 1. KYC verified
        if profile.kyc_status == "VERIFIED":
            factors["kyc_verified"] = 100
        elif profile.ocr_match_score:
            factors["kyc_verified"] = profile.ocr_match_score

        # 2. Income stability (dựa vào monthly_income)
        if profile.monthly_income:
            if profile.monthly_income >= 20000000:
                factors["income_stability"] = 100
            elif profile.monthly_income >= 10000000:
                factors["income_stability"] = 80
            elif profile.monthly_income >= 5000000:
                factors["income_stability"] = 60
            else:
                factors["income_stability"] = 40

        # 3. Loan history
        past_loans = LoanContract.objects.filter(
            loan_request__borrower=user, is_active=False
        ).count()

        if past_loans > 0:
            # Có lịch sử vay và đã trả
            factors["loan_history"] = min(100, 60 + past_loans * 10)
        else:
            factors["loan_history"] = 50  # New borrower

        # 4. Debt ratio (nếu có loan_request)
        if loan_request and profile.monthly_income:
            monthly_payment = float(loan_request.amount) / loan_request.duration_months
            debt_ratio = monthly_payment / float(profile.monthly_income) * 100

            if debt_ratio <= 30:
                factors["debt_ratio"] = 100
            elif debt_ratio <= 50:
                factors["debt_ratio"] = 70
            elif debt_ratio <= 70:
                factors["debt_ratio"] = 50
            else:
                factors["debt_ratio"] = 30
        else:
            factors["debt_ratio"] = 60

        # Calculate credit score
        weights = {
            "kyc_verified": 0.3,
            "income_stability": 0.25,
            "loan_history": 0.2,
            "debt_ratio": 0.25,
        }

        credit_score = sum(factors[k] * weights[k] * 10 for k in weights)
        credit_score = min(1000, max(0, int(credit_score)))

        # Determine risk level
        if credit_score >= 800:
            risk_level = "VERY_LOW"
        elif credit_score >= 650:
            risk_level = "LOW"
        elif credit_score >= 500:
            risk_level = "MEDIUM"
        elif credit_score >= 350:
            risk_level = "HIGH"
        else:
            risk_level = "VERY_HIGH"

        # Update risk profile
        risk_profile.credit_score = credit_score
        risk_profile.risk_level = risk_level
        risk_profile.income_stability = factors["income_stability"]
        risk_profile.payment_history_score = factors["loan_history"]
        risk_profile.debt_to_income_ratio = factors["debt_ratio"]
        risk_profile.ai_analysis = {
            "factors": factors,
            "weights": weights,
            "assessment_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        risk_profile.save()

        return {
            "credit_score": credit_score,
            "risk_level": risk_level,
            "factors": factors,
            "recommendation": self._get_risk_recommendation(risk_level),
        }

    def _get_risk_recommendation(self, risk_level: str) -> str:
        """Khuyến nghị dựa trên mức rủi ro"""
        recommendations = {
            "VERY_LOW": "Hồ sơ rất tốt. Đề xuất duyệt với lãi suất ưu đãi.",
            "LOW": "Hồ sơ tốt. Đề xuất duyệt.",
            "MEDIUM": "Hồ sơ trung bình. Cần xem xét thêm mục đích vay.",
            "HIGH": "Hồ sơ có rủi ro. Cân nhắc yêu cầu tài sản đảm bảo.",
            "VERY_HIGH": "Hồ sơ rủi ro cao. Không khuyến nghị cho vay.",
        }
        return recommendations.get(risk_level, "Cần đánh giá thêm")

    def _notify_kyc_result(self, user, profile):
        """Thông báo kết quả KYC"""
        if profile.kyc_status == "VERIFIED":
            self._create_notification(
                user=user,
                notification_type="KYC_STATUS",
                title="✓ Xác thực KYC thành công!",
                message=f"""Chúc mừng! Tài khoản của bạn đã được xác thực.
Độ khớp thông tin: {profile.ocr_match_score or 100}%
Bạn có thể bắt đầu vay và cho vay trên nền tảng.""",
            )
        elif profile.kyc_status == "REJECTED":
            self._create_notification(
                user=user,
                notification_type="KYC_STATUS",
                title="✗ Xác thực KYC không thành công",
                message=f"""Thông tin bạn nhập không khớp với CCCD.
Độ khớp: {profile.ocr_match_score or 0}%
Lý do: {profile.kyc_note or 'Thông tin không chính xác'}
Vui lòng kiểm tra và cập nhật lại thông tin.""",
            )

    def verify_kyc_with_ocr(self, user_id: int) -> Dict[str, Any]:
        """
        API để verify KYC với OCR

        Args:
            user_id: ID của user cần verify

        Returns:
            Kết quả xác minh
        """
        from django.contrib.auth.models import User
        from user.models import UserProfile, KYCDocument

        try:
            user = User.objects.get(id=user_id)
            profile = UserProfile.objects.get(user=user)
            kyc_docs = KYCDocument.objects.filter(user=user)

            result = self._perform_ocr_verification(user, profile, kyc_docs)

            return {
                "success": result["success"],
                "match_score": result.get("match_score", 0),
                "message": result.get("message", ""),
                "kyc_status": profile.kyc_status,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
