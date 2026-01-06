"""
Views cho User app - Quản lý người dùng, KYC, Profile
"""

import json
import os
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .models import UserProfile, KYCDocument


def register_view(request):
    """Đăng ký tài khoản mới"""
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password2 = request.POST.get("password2")

        if password != password2:
            messages.error(request, "Mật khẩu không khớp!")
            return render(request, "user/register.html")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Tên đăng nhập đã tồn tại!")
            return render(request, "user/register.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email đã được sử dụng!")
            return render(request, "user/register.html")

        user = User.objects.create_user(
            username=username, email=email, password=password
        )
        UserProfile.objects.create(user=user)

        login(request, user)
        messages.success(request, "Đăng ký thành công!")
        return redirect("user:dashboard")

    return render(request, "user/register.html")


def login_view(request):
    """Đăng nhập"""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Chào mừng {username}!")
            return redirect("user:dashboard")
        else:
            messages.error(request, "Sai tên đăng nhập hoặc mật khẩu!")

    return render(request, "user/login.html")


@login_required
def logout_view(request):
    """Đăng xuất"""
    logout(request)
    messages.info(request, "Đã đăng xuất!")
    return redirect("user:login")


@login_required
def dashboard_view(request):
    """Trang chủ sau đăng nhập"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    notifications = request.user.notifications.filter(is_read=False)[:5]

    loan_requests = (
        request.user.loan_requests.all()
        if hasattr(request.user, "loan_requests")
        else []
    )
    investments = (
        request.user.investments.all() if hasattr(request.user, "investments") else []
    )

    context = {
        "profile": profile,
        "notifications": notifications,
        "loan_requests": loan_requests[:5] if loan_requests else [],
        "investments": investments[:5] if investments else [],
    }
    return render(request, "user/dashboard.html", context)


@login_required
def profile_view(request):
    """Xem và cập nhật profile"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        profile.full_name = request.POST.get("full_name", "")
        profile.id_card_number = request.POST.get("id_card_number", "")
        profile.address = request.POST.get("address", "")
        profile.save()
        messages.success(request, "Cập nhật thông tin thành công!")
        return redirect("user:profile")

    return render(request, "user/profile.html", {"profile": profile})


@login_required
def kyc_view(request):
    """Trang xác thực KYC với form thông tin cá nhân chi tiết"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    kyc_docs = KYCDocument.objects.filter(user=request.user)

    if request.method == "POST":
        # Lưu thông tin cá nhân từ form
        profile.full_name = request.POST.get("full_name", "")
        profile.id_card_number = request.POST.get("id_card_number", "")
        profile.date_of_birth = request.POST.get("date_of_birth") or None
        profile.gender = request.POST.get("gender", "")
        profile.hometown = request.POST.get("hometown", "")
        profile.address = request.POST.get("address", "")
        profile.phone_number = request.POST.get("phone_number", "")
        profile.occupation = request.POST.get("occupation", "")
        profile.company_name = request.POST.get("company_name", "")

        monthly_income = request.POST.get("monthly_income", "0")
        try:
            profile.monthly_income = float(monthly_income.replace(",", ""))
        except:
            profile.monthly_income = 0

        profile.save()
        messages.success(request, "Đã lưu thông tin cá nhân!")
        return redirect("user:kyc")

    return render(request, "user/kyc.html", {"profile": profile, "kyc_docs": kyc_docs})


@login_required
@require_http_methods(["POST"])
def upload_kyc_document(request):
    """Upload tài liệu KYC và OCR bằng Vintern"""
    doc_type = request.POST.get("doc_type")
    image = request.FILES.get("image")

    if not image:
        return JsonResponse({"success": False, "error": "Chưa chọn file!"})

    # Xóa tài liệu cũ nếu có
    KYCDocument.objects.filter(user=request.user, doc_type=doc_type).delete()
    doc = KYCDocument.objects.create(user=request.user, doc_type=doc_type, image=image)
    doc.ocr_status = "PROCESSING"
    doc.save()

    # OCR bằng Vintern
    try:
        from ai_agents.services.vintern_ocr import vintern_ocr

        image_path = doc.image.path

        if doc_type == "ID_CARD_FRONT":
            ocr_result = vintern_ocr.extract_id_card_front(image_path)
        elif doc_type == "ID_CARD_BACK":
            ocr_result = vintern_ocr.extract_id_card_back(image_path)
        else:
            ocr_result = {"success": False, "error": "Loại tài liệu không hỗ trợ"}

        if ocr_result.get("success"):
            doc.ai_extracted_data = ocr_result.get("data", {})
            doc.ocr_status = "SUCCESS"

            # Lưu OCR data vào profile nếu là mặt trước
            if doc_type == "ID_CARD_FRONT":
                profile = request.user.profile
                profile.ocr_data = ocr_result.get("data", {})
                profile.save()
        else:
            doc.ocr_status = "FAILED"
            doc.ai_extracted_data = {"error": ocr_result.get("error", "OCR failed")}

        doc.save()

    except Exception as e:
        doc.ocr_status = "FAILED"
        doc.ai_extracted_data = {"error": str(e)}
        doc.save()

    profile = request.user.profile
    profile.kyc_status = "PENDING"
    profile.save()

    return JsonResponse(
        {
            "success": True,
            "message": "Upload thành công!",
            "doc_id": doc.id,
            "ocr_status": doc.ocr_status,
            "ocr_data": doc.ai_extracted_data,
        }
    )


@login_required
def submit_kyc(request):
    """Submit KYC để AI đánh giá và xác minh thông tin"""
    from ai_agents.agents import BorrowerProfilerAgent
    from ai_agents.services.vintern_ocr import vintern_ocr

    docs = KYCDocument.objects.filter(user=request.user)
    doc_types = [d.doc_type for d in docs]

    if "ID_CARD_FRONT" not in doc_types or "ID_CARD_BACK" not in doc_types:
        return JsonResponse({"success": False, "error": "Vui lòng upload đầy đủ CCCD!"})

    profile = request.user.profile

    # Lấy OCR data từ CCCD mặt trước
    id_front = docs.filter(doc_type="ID_CARD_FRONT").first()
    ocr_data = (
        id_front.ai_extracted_data if id_front and id_front.ai_extracted_data else {}
    )

    # So sánh thông tin người dùng nhập với OCR data
    user_data = {
        "full_name": profile.full_name,
        "id_number": profile.id_card_number,
        "date_of_birth": str(profile.date_of_birth) if profile.date_of_birth else "",
        "gender": profile.gender,
        "hometown": profile.hometown,
        "address": profile.address,
    }

    # Verify bằng LLM
    verify_result = vintern_ocr.verify_user_info(user_data, ocr_data)

    profile.ocr_verified = verify_result.get("is_verified", False)
    profile.ocr_match_score = verify_result.get("match_score", 0)
    profile.ocr_data = {
        "ocr": ocr_data,
        "user_input": user_data,
        "verification": verify_result,
    }

    # Gọi AI Agent để đánh giá tổng thể
    agent = BorrowerProfilerAgent()
    result = agent.process(request.user)

    if result["success"] and profile.ocr_match_score >= 70:
        profile.kyc_status = "VERIFIED"
        profile.save()
        return JsonResponse(
            {
                "success": True,
                "message": "Xác thực KYC thành công!",
                "data": result["data"],
                "verification": {
                    "is_verified": profile.ocr_verified,
                    "match_score": profile.ocr_match_score,
                    "details": verify_result.get("details", {}),
                },
            }
        )
    else:
        profile.kyc_status = "REJECTED"
        rejection_reason = []
        if profile.ocr_match_score < 70:
            rejection_reason.append(
                f"Thông tin không khớp (độ khớp: {profile.ocr_match_score}%)"
            )
            if verify_result.get("mismatches"):
                rejection_reason.append(
                    f"Các trường không khớp: {', '.join(verify_result.get('mismatches', []))}"
                )
        if not result["success"]:
            rejection_reason.append(result.get("error", "Lỗi AI đánh giá"))

        profile.kyc_note = "; ".join(rejection_reason)
        profile.save()

        return JsonResponse(
            {
                "success": False,
                "error": profile.kyc_note,
                "verification": {
                    "is_verified": profile.ocr_verified,
                    "match_score": profile.ocr_match_score,
                    "details": verify_result.get("details", {}),
                    "mismatches": verify_result.get("mismatches", []),
                },
            }
        )


@login_required
def notifications_view(request):
    """Xem tất cả thông báo"""
    notifications = request.user.notifications.all().order_by("-created_at")
    return render(request, "user/notifications.html", {"notifications": notifications})


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Đánh dấu thông báo đã đọc"""
    notification = get_object_or_404(request.user.notifications, id=notification_id)
    notification.is_read = True
    notification.save()
    return JsonResponse({"success": True})


@login_required
def wallet_view(request):
    """Xem ví tiền"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(
        request, "user/wallet.html", {"profile": profile, "balance": profile.balance}
    )


@login_required
@require_http_methods(["POST"])
def deposit(request):
    """Nạp tiền vào ví"""
    try:
        amount = float(request.POST.get("amount", 0))
        if amount <= 0:
            return JsonResponse({"success": False, "error": "Số tiền không hợp lệ!"})

        profile = request.user.profile
        profile.balance += amount
        profile.save()
        return JsonResponse(
            {
                "success": True,
                "message": f"Nạp {amount:,.0f} VNĐ thành công!",
                "new_balance": float(profile.balance),
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@require_http_methods(["POST"])
def withdraw(request):
    """Rút tiền từ ví"""
    try:
        amount = float(request.POST.get("amount", 0))
        profile = request.user.profile

        if amount <= 0:
            return JsonResponse({"success": False, "error": "Số tiền không hợp lệ!"})
        if amount > float(profile.balance):
            return JsonResponse({"success": False, "error": "Số dư không đủ!"})

        profile.balance -= amount
        profile.save()
        return JsonResponse(
            {
                "success": True,
                "message": f"Rút {amount:,.0f} VNĐ thành công!",
                "new_balance": float(profile.balance),
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})
