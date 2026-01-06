"""
Views cho Lending app - Quản lý vay/cho vay
"""

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import LoanRequest, LoanContract, RepaymentSchedule, Dispute, LenderProfile


# ========== BORROWER VIEWS ==========


@login_required
def create_loan_request(request):
    """Tạo đơn vay mới"""
    if request.method == "POST":
        # Check KYC
        if (
            not hasattr(request.user, "profile")
            or request.user.profile.kyc_status != "VERIFIED"
        ):
            messages.error(request, "Vui lòng hoàn thành KYC trước khi vay!")
            return redirect("user:kyc")

        amount = Decimal(request.POST.get("amount", 0))
        interest_rate = float(request.POST.get("interest_rate", 12))
        duration_months = int(request.POST.get("duration_months", 6))
        purpose = request.POST.get("purpose", "")

        if amount < 1000000:
            messages.error(request, "Số tiền vay tối thiểu 1,000,000 VNĐ!")
            return render(request, "lending/create_loan.html")

        loan = LoanRequest.objects.create(
            borrower=request.user,
            amount=amount,
            interest_rate=interest_rate,
            duration_months=duration_months,
            purpose=purpose,
            status="PENDING",
        )

        # Run AI profiler
        from ai_agents.agents import BorrowerProfilerAgent

        agent = BorrowerProfilerAgent()
        result = agent.process(request.user, loan)

        # Nếu khoản vay được duyệt, tìm lender phù hợp và thông báo
        if loan.status == "APPROVED":
            from ai_agents.services.matching import loan_matching

            lender_count = loan_matching.notify_matching_lenders(loan)

            if lender_count > 0:
                loan_matching.notify_borrower_has_match(loan, lender_count)
                messages.success(
                    request,
                    f"Đơn vay đã được duyệt! Có {lender_count} người cho vay phù hợp đã được thông báo.",
                )
            else:
                loan_matching.notify_borrower_no_match(loan)
                messages.success(
                    request,
                    "Đơn vay đã được duyệt! Hệ thống sẽ thông báo khi có người cho vay phù hợp.",
                )
        else:
            messages.success(request, "Đơn vay đã được tạo! Đang chờ duyệt.")

        return redirect("lending:my_loans")

    return render(request, "lending/create_loan.html")


@login_required
def my_loans(request):
    """Danh sách đơn vay của tôi"""
    loans = LoanRequest.objects.filter(borrower=request.user).order_by("-created_at")
    return render(request, "lending/my_loans.html", {"loans": loans})


@login_required
def loan_detail(request, loan_id):
    """Chi tiết đơn vay"""
    loan = get_object_or_404(LoanRequest, id=loan_id)

    # Check permission
    is_borrower = loan.borrower == request.user
    is_lender = (
        hasattr(loan, "loancontract") and loan.loancontract.lender == request.user
    )

    if not is_borrower and not is_lender:
        messages.error(request, "Bạn không có quyền xem đơn vay này!")
        return redirect("user:dashboard")

    contract = getattr(loan, "loancontract", None)
    schedules = contract.schedules.all() if contract else []

    return render(
        request,
        "lending/loan_detail.html",
        {
            "loan": loan,
            "contract": contract,
            "schedules": schedules,
            "is_borrower": is_borrower,
            "is_lender": is_lender,
        },
    )


# ========== LENDER VIEWS ==========


@login_required
def lender_profile_view(request):
    """Cấu hình profile người cho vay"""
    profile, created = LenderProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        profile.min_amount = Decimal(request.POST.get("min_amount", 1000000))
        profile.max_amount = Decimal(request.POST.get("max_amount", 100000000))
        profile.min_interest_rate = float(request.POST.get("min_interest_rate", 8))
        profile.preferred_duration_min = int(
            request.POST.get("preferred_duration_min", 1)
        )
        profile.preferred_duration_max = int(
            request.POST.get("preferred_duration_max", 24)
        )
        profile.risk_tolerance = request.POST.get("risk_tolerance", "MEDIUM")
        profile.is_active = request.POST.get("is_active") == "on"
        profile.save()

        # Tìm và thông báo các khoản vay phù hợp
        if profile.is_active:
            from ai_agents.services.matching import loan_matching

            loan_count = loan_matching.notify_matching_loans(profile)

            if loan_count > 0:
                messages.success(
                    request,
                    f"Cập nhật thành công! Tìm thấy {loan_count} khoản vay phù hợp.",
                )
            else:
                messages.success(
                    request,
                    "Cập nhật thành công! Chưa có khoản vay phù hợp, hệ thống sẽ thông báo khi có.",
                )
        else:
            messages.success(request, "Cập nhật thành công!")

        return redirect("lending:lender_profile")

    # Lấy danh sách khoản vay phù hợp để hiển thị
    matching_loans = []
    if profile.is_active:
        from ai_agents.services.matching import loan_matching

        matching_loans = loan_matching.find_matching_loans(profile)[:10]

    return render(
        request,
        "lending/lender_profile.html",
        {"profile": profile, "matching_loans": matching_loans},
    )


@login_required
def browse_loans(request):
    """Duyệt danh sách đơn vay có thể đầu tư"""
    loans = LoanRequest.objects.filter(status="APPROVED").exclude(borrower=request.user)

    # Tính match score cho mỗi loan
    matching_loans = []

    if hasattr(request.user, "lender_profile"):
        from ai_agents.services.matching import loan_matching

        lp = request.user.lender_profile

        # Lấy loans phù hợp với match score
        matches = loan_matching.find_matching_loans(lp)

        # Tạo dict để lookup nhanh
        match_dict = {m["loan"].id: m for m in matches}

        for loan in loans:
            if loan.id in match_dict:
                matching_loans.append(
                    {
                        "loan": loan,
                        "match_score": match_dict[loan.id]["match_score"],
                        "reasons": match_dict[loan.id]["reasons"],
                    }
                )
            else:
                matching_loans.append({"loan": loan, "match_score": 0, "reasons": []})

        # Sắp xếp theo match score
        matching_loans.sort(key=lambda x: x["match_score"], reverse=True)
    else:
        # Không có lender profile, hiển thị tất cả
        matching_loans = [
            {"loan": loan, "match_score": None, "reasons": []} for loan in loans
        ]

    return render(
        request, "lending/browse_loans.html", {"matching_loans": matching_loans}
    )


@login_required
def invest_in_loan(request, loan_id):
    """Đầu tư vào đơn vay"""
    loan = get_object_or_404(LoanRequest, id=loan_id, status="APPROVED")

    if loan.borrower == request.user:
        return JsonResponse({"success": False, "error": "Không thể tự cho vay!"})

    # Check balance
    profile = request.user.profile
    if profile.balance < loan.amount:
        return JsonResponse({"success": False, "error": "Số dư không đủ!"})

    # Deduct balance
    profile.balance -= loan.amount
    profile.save()

    # Add to borrower
    borrower_profile = loan.borrower.profile
    borrower_profile.balance += loan.amount
    borrower_profile.save()

    # Generate contract
    from ai_agents.agents import ContractGeneratorAgent

    agent = ContractGeneratorAgent()
    result = agent.process(loan, request.user)

    if result["success"]:
        # Update lender stats
        if hasattr(request.user, "lender_profile"):
            lp = request.user.lender_profile
            lp.total_invested += loan.amount
            lp.active_investments += 1
            lp.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Đầu tư thành công!",
                "contract_id": result["data"]["contract_id"],
            }
        )
    else:
        # Rollback
        profile.balance += loan.amount
        profile.save()
        borrower_profile.balance -= loan.amount
        borrower_profile.save()
        return JsonResponse(
            {"success": False, "error": result.get("error", "Lỗi tạo hợp đồng")}
        )


@login_required
def my_investments(request):
    """Danh sách đầu tư của tôi"""
    investments = LoanContract.objects.filter(lender=request.user).order_by(
        "-signed_date"
    )
    return render(request, "lending/my_investments.html", {"investments": investments})


# ========== REPAYMENT VIEWS ==========


@login_required
def make_payment(request, schedule_id):
    """Thanh toán kỳ hạn"""
    schedule = get_object_or_404(RepaymentSchedule, id=schedule_id)
    contract = schedule.contract

    if contract.loan_request.borrower != request.user:
        return JsonResponse({"success": False, "error": "Không có quyền!"})

    if schedule.is_paid:
        return JsonResponse({"success": False, "error": "Kỳ hạn này đã thanh toán!"})

    # Check balance
    profile = request.user.profile
    if profile.balance < schedule.amount_due:
        return JsonResponse({"success": False, "error": "Số dư không đủ!"})

    # Transfer money
    profile.balance -= schedule.amount_due
    profile.save()

    lender_profile = contract.lender.profile
    lender_profile.balance += schedule.amount_due
    lender_profile.save()

    # Mark as paid
    from ai_agents.agents import PaymentMonitorAgent

    agent = PaymentMonitorAgent()
    result = agent.mark_payment_completed(schedule_id)

    return JsonResponse(result)


# ========== DISPUTE VIEWS ==========


@login_required
def create_dispute(request, contract_id):
    """Tạo tranh chấp"""
    contract = get_object_or_404(LoanContract, id=contract_id)

    is_borrower = contract.loan_request.borrower == request.user
    is_lender = contract.lender == request.user

    if not is_borrower and not is_lender:
        return JsonResponse({"success": False, "error": "Không có quyền!"})

    if request.method == "POST":
        dispute_type = request.POST.get("dispute_type")
        description = request.POST.get("description")

        dispute = Dispute.objects.create(
            contract=contract,
            raised_by=request.user,
            dispute_type=dispute_type,
            description=description,
        )

        # Run AI resolver
        from ai_agents.agents import DisputeResolverAgent

        agent = DisputeResolverAgent()
        agent.process(dispute)

        messages.success(request, "Tranh chấp đã được ghi nhận!")
        return redirect("lending:dispute_detail", dispute_id=dispute.id)

    return render(request, "lending/create_dispute.html", {"contract": contract})


@login_required
def dispute_detail(request, dispute_id):
    """Chi tiết tranh chấp"""
    dispute = get_object_or_404(Dispute, id=dispute_id)

    is_borrower = dispute.contract.loan_request.borrower == request.user
    is_lender = dispute.contract.lender == request.user

    if not is_borrower and not is_lender:
        messages.error(request, "Không có quyền!")
        return redirect("user:dashboard")

    return render(request, "lending/dispute_detail.html", {"dispute": dispute})


@login_required
def my_disputes(request):
    """Danh sách tranh chấp của tôi"""
    disputes = Dispute.objects.filter(raised_by=request.user).order_by("-created_at")
    return render(request, "lending/my_disputes.html", {"disputes": disputes})
