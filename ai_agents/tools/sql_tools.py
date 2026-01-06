"""
SQL Tools cho P2P Lending Platform
Tham khảo từ Fintech project
"""

from langchain.tools import tool
from django.db.models import Q, F, Avg, Count
from decimal import Decimal
from typing import List, Dict, Any, Optional


# ============== LOAN SEARCH TOOLS ==============


@tool("search_loans_by_interest_rate")
def search_loans_by_interest_rate(
    min_rate: float, max_rate: float, limit: int = 20
) -> str:
    """
    Tìm kiếm các khoản vay theo khoảng lãi suất.
    Args:
        min_rate: Lãi suất tối thiểu (%/năm)
        max_rate: Lãi suất tối đa (%/năm)
        limit: Số lượng kết quả tối đa
    Returns:
        Danh sách các khoản vay phù hợp
    """
    from lending.models import LoanRequest

    loans = LoanRequest.objects.filter(
        status="APPROVED", interest_rate__gte=min_rate, interest_rate__lte=max_rate
    ).order_by("-created_at")[:limit]

    if not loans:
        return (
            f"Không tìm thấy khoản vay nào với lãi suất từ {min_rate}% đến {max_rate}%"
        )

    results = []
    for loan in loans:
        results.append(
            f"- ID: {loan.id}, Số tiền: {loan.amount:,.0f} VNĐ, "
            f"Lãi suất: {loan.interest_rate}%/năm, Kỳ hạn: {loan.duration_months} tháng, "
            f"Người vay: {loan.borrower.username}"
        )

    return f"Tìm thấy {len(results)} khoản vay:\n" + "\n".join(results)


@tool("search_loans_by_amount")
def search_loans_by_amount(
    min_amount: float, max_amount: float, limit: int = 20
) -> str:
    """
    Tìm kiếm các khoản vay theo khoảng số tiền.
    Args:
        min_amount: Số tiền tối thiểu (VNĐ)
        max_amount: Số tiền tối đa (VNĐ)
        limit: Số lượng kết quả tối đa
    Returns:
        Danh sách các khoản vay phù hợp
    """
    from lending.models import LoanRequest

    loans = LoanRequest.objects.filter(
        status="APPROVED",
        amount__gte=Decimal(str(min_amount)),
        amount__lte=Decimal(str(max_amount)),
    ).order_by("-created_at")[:limit]

    if not loans:
        return f"Không tìm thấy khoản vay nào với số tiền từ {min_amount:,.0f} đến {max_amount:,.0f} VNĐ"

    results = []
    for loan in loans:
        results.append(
            f"- ID: {loan.id}, Số tiền: {loan.amount:,.0f} VNĐ, "
            f"Lãi suất: {loan.interest_rate}%/năm, Kỳ hạn: {loan.duration_months} tháng"
        )

    return f"Tìm thấy {len(results)} khoản vay:\n" + "\n".join(results)


@tool("search_loans_by_duration")
def search_loans_by_duration(min_months: int, max_months: int, limit: int = 20) -> str:
    """
    Tìm kiếm các khoản vay theo kỳ hạn.
    Args:
        min_months: Kỳ hạn tối thiểu (tháng)
        max_months: Kỳ hạn tối đa (tháng)
        limit: Số lượng kết quả tối đa
    Returns:
        Danh sách các khoản vay phù hợp
    """
    from lending.models import LoanRequest

    loans = LoanRequest.objects.filter(
        status="APPROVED",
        duration_months__gte=min_months,
        duration_months__lte=max_months,
    ).order_by("-created_at")[:limit]

    if not loans:
        return f"Không tìm thấy khoản vay nào với kỳ hạn từ {min_months} đến {max_months} tháng"

    results = []
    for loan in loans:
        results.append(
            f"- ID: {loan.id}, Số tiền: {loan.amount:,.0f} VNĐ, "
            f"Lãi suất: {loan.interest_rate}%/năm, Kỳ hạn: {loan.duration_months} tháng"
        )

    return f"Tìm thấy {len(results)} khoản vay:\n" + "\n".join(results)


@tool("search_loans_advanced")
def search_loans_advanced(
    min_amount: float = 0,
    max_amount: float = 999999999999,
    min_rate: float = 0,
    max_rate: float = 100,
    min_months: int = 1,
    max_months: int = 120,
    limit: int = 20,
) -> str:
    """
    Tìm kiếm nâng cao các khoản vay với nhiều tiêu chí.
    Args:
        min_amount: Số tiền tối thiểu (VNĐ)
        max_amount: Số tiền tối đa (VNĐ)
        min_rate: Lãi suất tối thiểu (%/năm)
        max_rate: Lãi suất tối đa (%/năm)
        min_months: Kỳ hạn tối thiểu (tháng)
        max_months: Kỳ hạn tối đa (tháng)
        limit: Số lượng kết quả tối đa
    Returns:
        Danh sách các khoản vay phù hợp
    """
    from lending.models import LoanRequest

    loans = LoanRequest.objects.filter(
        status="APPROVED",
        amount__gte=Decimal(str(min_amount)),
        amount__lte=Decimal(str(max_amount)),
        interest_rate__gte=min_rate,
        interest_rate__lte=max_rate,
        duration_months__gte=min_months,
        duration_months__lte=max_months,
    ).order_by("-interest_rate")[:limit]

    if not loans:
        return "Không tìm thấy khoản vay nào phù hợp với tiêu chí"

    results = []
    for loan in loans:
        results.append(
            f"- ID: {loan.id}, Số tiền: {loan.amount:,.0f} VNĐ, "
            f"Lãi suất: {loan.interest_rate}%/năm, Kỳ hạn: {loan.duration_months} tháng, "
            f"Mục đích: {loan.purpose[:50]}..."
        )

    return f"Tìm thấy {len(results)} khoản vay:\n" + "\n".join(results)


@tool("get_loan_detail")
def get_loan_detail(loan_id: int) -> str:
    """
    Lấy thông tin chi tiết của một khoản vay.
    Args:
        loan_id: ID của khoản vay
    Returns:
        Thông tin chi tiết khoản vay
    """
    from lending.models import LoanRequest

    try:
        loan = LoanRequest.objects.get(id=loan_id)

        # Lấy thông tin borrower
        borrower = loan.borrower
        profile = getattr(borrower, "profile", None)
        risk_profile = getattr(borrower, "risk_profile", None)

        info = f"""
Thông tin khoản vay #{loan.id}:
- Số tiền: {loan.amount:,.0f} VNĐ
- Lãi suất: {loan.interest_rate}%/năm
- Kỳ hạn: {loan.duration_months} tháng
- Mục đích: {loan.purpose}
- Trạng thái: {loan.get_status_display()}
- Ngày tạo: {loan.created_at.strftime('%d/%m/%Y %H:%M')}

Thông tin người vay:
- Username: {borrower.username}
- Tên: {profile.full_name if profile else 'N/A'}
- KYC: {profile.kyc_status if profile else 'N/A'}
"""
        if risk_profile:
            info += f"""
Hồ sơ rủi ro:
- Điểm tín dụng: {risk_profile.credit_score}/1000
- Mức rủi ro: {risk_profile.get_risk_level_display()}
"""
        return info

    except LoanRequest.DoesNotExist:
        return f"Không tìm thấy khoản vay với ID: {loan_id}"


# ============== USER/LENDER TOOLS ==============


@tool("get_lender_preferences")
def get_lender_preferences(user_id: int) -> str:
    """
    Lấy tiêu chí đầu tư của người cho vay.
    Args:
        user_id: ID của user
    Returns:
        Thông tin tiêu chí đầu tư
    """
    from lending.models import LenderProfile
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        profile = LenderProfile.objects.get(user=user)

        return f"""
Tiêu chí đầu tư của {user.username}:
- Số tiền: {profile.min_amount:,.0f} - {profile.max_amount:,.0f} VNĐ
- Lãi suất tối thiểu: {profile.min_interest_rate}%/năm
- Kỳ hạn: {profile.preferred_duration_min} - {profile.preferred_duration_max} tháng
- Mức chấp nhận rủi ro: {profile.get_risk_tolerance_display()}
- Đang hoạt động: {'Có' if profile.is_active else 'Không'}
"""
    except (User.DoesNotExist, LenderProfile.DoesNotExist):
        return f"Không tìm thấy hồ sơ người cho vay với user_id: {user_id}"


@tool("get_user_balance")
def get_user_balance(user_id: int) -> str:
    """
    Lấy số dư ví của user.
    Args:
        user_id: ID của user
    Returns:
        Số dư ví
    """
    from user.models import UserProfile
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        profile = UserProfile.objects.get(user=user)
        return f"Số dư ví của {user.username}: {profile.balance:,.0f} VNĐ"
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        return f"Không tìm thấy user với ID: {user_id}"


@tool("get_user_kyc_status")
def get_user_kyc_status(user_id: int) -> str:
    """
    Kiểm tra trạng thái KYC của user.
    Args:
        user_id: ID của user
    Returns:
        Trạng thái KYC và thông tin xác thực
    """
    from user.models import UserProfile, KYCDocument
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        profile = UserProfile.objects.get(user=user)
        docs = KYCDocument.objects.filter(user=user)

        doc_status = []
        for doc in docs:
            doc_status.append(f"  - {doc.get_doc_type_display()}: {doc.ocr_status}")

        return f"""
Trạng thái KYC của {user.username}:
- Trạng thái: {profile.get_kyc_status_display()}
- Độ khớp OCR: {profile.ocr_match_score or 0}%
- Đã xác thực: {'Có' if profile.ocr_verified else 'Không'}
Tài liệu:
{chr(10).join(doc_status) if doc_status else '  Chưa có tài liệu'}
"""
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        return f"Không tìm thấy user với ID: {user_id}"


# ============== STATISTICS TOOLS ==============


@tool("get_loan_statistics")
def get_loan_statistics() -> str:
    """
    Lấy thống kê tổng quan về các khoản vay trên sàn.
    Returns:
        Thống kê khoản vay
    """
    from lending.models import LoanRequest, LoanContract
    from django.db.models import Sum, Avg, Count

    stats = LoanRequest.objects.aggregate(
        total_count=Count("id"),
        pending_count=Count("id", filter=Q(status="PENDING")),
        approved_count=Count("id", filter=Q(status="APPROVED")),
        funded_count=Count("id", filter=Q(status="FUNDED")),
        total_amount=Sum("amount"),
        avg_amount=Avg("amount"),
        avg_rate=Avg("interest_rate"),
        avg_duration=Avg("duration_months"),
    )

    funded_amount = (
        LoanContract.objects.aggregate(total=Sum("loan_request__amount"))["total"] or 0
    )

    return f"""
Thống kê khoản vay trên sàn:
- Tổng số đơn vay: {stats['total_count']}
- Đang chờ duyệt: {stats['pending_count']}
- Đã duyệt (chờ đầu tư): {stats['approved_count']}
- Đã giải ngân: {stats['funded_count']}
- Tổng giá trị đơn vay: {stats['total_amount'] or 0:,.0f} VNĐ
- Đã giải ngân: {funded_amount:,.0f} VNĐ
- Số tiền vay trung bình: {stats['avg_amount'] or 0:,.0f} VNĐ
- Lãi suất trung bình: {stats['avg_rate'] or 0:.1f}%/năm
- Kỳ hạn trung bình: {stats['avg_duration'] or 0:.0f} tháng
"""


@tool("find_matching_lenders_for_loan")
def find_matching_lenders_for_loan(loan_id: int) -> str:
    """
    Tìm các người cho vay phù hợp với một khoản vay cụ thể.
    Args:
        loan_id: ID của khoản vay
    Returns:
        Danh sách người cho vay phù hợp
    """
    from lending.models import LoanRequest, LenderProfile

    try:
        loan = LoanRequest.objects.get(id=loan_id)
    except LoanRequest.DoesNotExist:
        return f"Không tìm thấy khoản vay với ID: {loan_id}"

    # Tìm lender phù hợp
    lenders = LenderProfile.objects.filter(
        is_active=True,
        min_amount__lte=loan.amount,
        max_amount__gte=loan.amount,
        min_interest_rate__lte=loan.interest_rate,
        preferred_duration_min__lte=loan.duration_months,
        preferred_duration_max__gte=loan.duration_months,
    ).exclude(user=loan.borrower)

    if not lenders:
        return f"Không tìm thấy người cho vay phù hợp với khoản vay #{loan_id}"

    results = []
    for lp in lenders:
        balance = (
            getattr(lp.user.profile, "balance", 0) if hasattr(lp.user, "profile") else 0
        )
        results.append(
            f"- {lp.user.username}: Số dư {balance:,.0f} VNĐ, "
            f"Chấp nhận rủi ro: {lp.get_risk_tolerance_display()}"
        )

    return f"Tìm thấy {len(results)} người cho vay phù hợp:\n" + "\n".join(results)


# Export all tools
LOAN_SEARCH_TOOLS = [
    search_loans_by_interest_rate,
    search_loans_by_amount,
    search_loans_by_duration,
    search_loans_advanced,
    get_loan_detail,
]

LENDER_TOOLS = [
    get_lender_preferences,
    get_user_balance,
    get_user_kyc_status,
    find_matching_lenders_for_loan,
]

STATISTICS_TOOLS = [
    get_loan_statistics,
]

ALL_TOOLS = LOAN_SEARCH_TOOLS + LENDER_TOOLS + STATISTICS_TOOLS
