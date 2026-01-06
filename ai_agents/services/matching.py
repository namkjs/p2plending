"""
Loan Matching Service - Kết nối người vay và người cho vay
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db.models import Q, F
from django.contrib.auth.models import User

from lending.models import LoanRequest, LenderProfile, LenderMatchResult
from ai_agents.models import Notification


class LoanMatchingService:
    """Service để matching khoản vay với người cho vay phù hợp"""

    def find_matching_lenders(self, loan: LoanRequest) -> List[Dict[str, Any]]:
        """
        Tìm người cho vay phù hợp với khoản vay

        Returns:
            List các lender profile phù hợp với match score
        """
        matching_lenders = []

        # Lấy tất cả lender profile đang active
        lender_profiles = LenderProfile.objects.filter(is_active=True).exclude(
            user=loan.borrower  # Không cho vay chính mình
        )

        for lp in lender_profiles:
            match_score = self._calculate_match_score(loan, lp)
            if match_score >= 50:  # Chỉ lấy những lender match >= 50%
                matching_lenders.append(
                    {
                        "lender_profile": lp,
                        "match_score": match_score,
                        "reasons": self._get_match_reasons(loan, lp),
                    }
                )

        # Sắp xếp theo match score
        matching_lenders.sort(key=lambda x: x["match_score"], reverse=True)

        return matching_lenders

    def _calculate_match_score(self, loan: LoanRequest, lender: LenderProfile) -> float:
        """Tính điểm phù hợp giữa loan và lender"""
        score = 0
        weights = {"amount": 30, "duration": 25, "interest_rate": 25, "risk": 20}

        # 1. Amount match
        if lender.min_amount <= loan.amount <= lender.max_amount:
            score += weights["amount"]
        elif loan.amount < lender.min_amount:
            # Partial score
            ratio = float(loan.amount / lender.min_amount)
            score += weights["amount"] * ratio * 0.5
        elif loan.amount > lender.max_amount:
            ratio = float(lender.max_amount / loan.amount)
            score += weights["amount"] * ratio * 0.5

        # 2. Duration match
        if (
            lender.preferred_duration_min
            <= loan.duration_months
            <= lender.preferred_duration_max
        ):
            score += weights["duration"]
        else:
            # Partial score
            if loan.duration_months < lender.preferred_duration_min:
                diff = lender.preferred_duration_min - loan.duration_months
            else:
                diff = loan.duration_months - lender.preferred_duration_max
            score += max(0, weights["duration"] - diff * 2)

        # 3. Interest rate match
        if loan.interest_rate >= lender.min_interest_rate:
            score += weights["interest_rate"]
        else:
            diff = lender.min_interest_rate - loan.interest_rate
            score += max(0, weights["interest_rate"] - diff * 5)

        # 4. Risk match (based on borrower profile)
        if hasattr(loan.borrower, "risk_profile"):
            risk = loan.borrower.risk_profile.risk_level
            if lender.risk_tolerance == "HIGH":
                score += weights["risk"]  # Accept all
            elif lender.risk_tolerance == "MEDIUM" and risk in ["LOW", "MEDIUM"]:
                score += weights["risk"]
            elif lender.risk_tolerance == "LOW" and risk == "LOW":
                score += weights["risk"]
            else:
                score += weights["risk"] * 0.5  # Partial
        else:
            score += weights["risk"] * 0.7  # Unknown risk

        return min(100, score)

    def _get_match_reasons(self, loan: LoanRequest, lender: LenderProfile) -> List[str]:
        """Lấy lý do match"""
        reasons = []

        if lender.min_amount <= loan.amount <= lender.max_amount:
            reasons.append("Số tiền vay phù hợp")

        if (
            lender.preferred_duration_min
            <= loan.duration_months
            <= lender.preferred_duration_max
        ):
            reasons.append("Kỳ hạn phù hợp")

        if loan.interest_rate >= lender.min_interest_rate:
            reasons.append("Lãi suất đạt yêu cầu")

        return reasons

    def find_matching_loans(self, lender: LenderProfile) -> List[Dict[str, Any]]:
        """
        Tìm khoản vay phù hợp với người cho vay
        """
        # Lọc các khoản vay APPROVED và chưa có người cho vay
        loans = (
            LoanRequest.objects.filter(status="APPROVED")
            .exclude(borrower=lender.user)
            .filter(loancontract__isnull=True)  # Chưa có contract
        )

        matching_loans = []
        for loan in loans:
            match_score = self._calculate_match_score(loan, lender)
            if match_score >= 50:
                matching_loans.append(
                    {
                        "loan": loan,
                        "match_score": match_score,
                        "reasons": self._get_match_reasons(loan, lender),
                    }
                )

        matching_loans.sort(key=lambda x: x["match_score"], reverse=True)
        return matching_loans

    def save_match_results(self, loan: LoanRequest, matches: List[Dict]) -> None:
        """Lưu kết quả matching vào database"""
        # Xóa matches cũ
        LenderMatchResult.objects.filter(loan_request=loan).delete()

        for match in matches:
            LenderMatchResult.objects.create(
                loan_request=loan,
                lender=match["lender_profile"].user,
                match_score=match["match_score"],
                match_reasons=match["reasons"],
            )

    def notify_matching_lenders(self, loan: LoanRequest) -> int:
        """
        Thông báo cho các lender phù hợp khi có khoản vay mới

        Returns:
            Số lượng lender được thông báo
        """
        matches = self.find_matching_lenders(loan)
        self.save_match_results(loan, matches)

        count = 0
        for match in matches:
            lender = match["lender_profile"].user
            Notification.objects.create(
                user=lender,
                notification_type="LOAN_MATCH",
                title="Có khoản vay phù hợp mới!",
                message=f"""Khoản vay {loan.amount:,.0f} VNĐ với lãi suất {loan.interest_rate}%/năm, kỳ hạn {loan.duration_months} tháng.
Độ phù hợp: {match['match_score']:.0f}%
{', '.join(match['reasons'])}""",
                related_loan=loan,
            )
            count += 1

        return count

    def notify_matching_loans(self, lender: LenderProfile) -> int:
        """
        Thông báo cho lender về các khoản vay phù hợp (khi lender mới đăng ký hoặc cập nhật profile)

        Returns:
            Số lượng loan được thông báo
        """
        matches = self.find_matching_loans(lender)

        if matches:
            # Gửi 1 thông báo tổng hợp
            loans_info = []
            for match in matches[:5]:  # Max 5 loans
                loan = match["loan"]
                loans_info.append(
                    f"- {loan.amount:,.0f} VNĐ, {loan.interest_rate}%/năm, {loan.duration_months} tháng ({match['match_score']:.0f}% phù hợp)"
                )

            Notification.objects.create(
                user=lender.user,
                notification_type="LOAN_MATCH",
                title=f"Tìm thấy {len(matches)} khoản vay phù hợp!",
                message="Các khoản vay phù hợp với tiêu chí của bạn:\n"
                + "\n".join(loans_info),
            )

        return len(matches)

    def notify_borrower_no_match(self, loan: LoanRequest) -> None:
        """Thông báo cho borrower khi chưa có lender phù hợp"""
        matches = self.find_matching_lenders(loan)

        if not matches:
            Notification.objects.create(
                user=loan.borrower,
                notification_type="SYSTEM",
                title="Khoản vay đang chờ người cho vay",
                message=f"""Khoản vay {loan.amount:,.0f} VNĐ của bạn đã được duyệt và đang chờ người cho vay phù hợp.
Hệ thống sẽ tự động thông báo khi có người quan tâm.""",
                related_loan=loan,
            )

    def notify_borrower_has_match(self, loan: LoanRequest, lender_count: int) -> None:
        """Thông báo cho borrower khi có lender quan tâm"""
        Notification.objects.create(
            user=loan.borrower,
            notification_type="LOAN_MATCH",
            title=f"Có {lender_count} người cho vay quan tâm!",
            message=f"Khoản vay {loan.amount:,.0f} VNĐ của bạn đang được {lender_count} người cho vay quan tâm.",
            related_loan=loan,
        )


# Singleton instance
loan_matching = LoanMatchingService()
