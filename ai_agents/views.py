"""
Views cho AI Agents - API endpoints để gọi các Agent
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import AgentLog, Notification
from lending.models import LenderMatchResult


@login_required
def agent_logs_view(request):
    """Xem lịch sử hoạt động Agent"""
    logs = AgentLog.objects.filter(user=request.user).order_by("-created_at")[:50]
    return render(request, "ai_agents/logs.html", {"logs": logs})


@login_required
@require_http_methods(["POST"])
def run_borrower_profiler(request):
    """Chạy Agent Borrower Profiler"""
    from .agents import BorrowerProfilerAgent

    agent = BorrowerProfilerAgent()
    result = agent.process(request.user)
    return JsonResponse(result)


@login_required
@require_http_methods(["POST"])
def run_lender_matcher(request, loan_id):
    """Chạy Agent Lender Matcher"""
    from lending.models import LoanRequest
    from .agents import LenderMatcherAgent

    loan = LoanRequest.objects.get(id=loan_id, borrower=request.user)
    agent = LenderMatcherAgent()
    result = agent.process(loan)
    return JsonResponse(result)


@login_required
def get_matches(request, loan_id):
    """Lấy danh sách matching cho đơn vay"""
    from lending.models import LoanRequest

    loan = LoanRequest.objects.get(id=loan_id, borrower=request.user)
    matches = LenderMatchResult.objects.filter(loan_request=loan).order_by(
        "-match_score"
    )

    data = [
        {
            "lender": m.lender.username,
            "match_score": m.match_score,
            "match_reasons": m.match_reasons,
            "status": m.status,
        }
        for m in matches
    ]

    return JsonResponse({"success": True, "matches": data})


@login_required
@require_http_methods(["POST"])
def approve_loan(request, loan_id):
    """Admin: Duyệt đơn vay (sau khi AI phân tích)"""
    from lending.models import LoanRequest
    from .agents import LenderMatcherAgent

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Không có quyền!"})

    loan = LoanRequest.objects.get(id=loan_id)
    loan.status = "APPROVED"
    loan.save()

    # Auto run matcher
    agent = LenderMatcherAgent()
    agent.process(loan)

    return JsonResponse({"success": True, "message": "Đơn vay đã được duyệt!"})


@login_required
@require_http_methods(["POST"])
def run_payment_check(request):
    """Admin: Chạy kiểm tra thanh toán"""
    from .agents import PaymentMonitorAgent

    if not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Không có quyền!"})

    agent = PaymentMonitorAgent()
    result = agent.process()
    return JsonResponse(result)


@login_required
@require_http_methods(["POST"])
def chat_send(request):
    """API Chat với Bot"""
    import json
    from .agents.chatbot_agent import ChatbotAgent

    try:
        data = json.loads(request.body)
        message = data.get("message")
        session_id = data.get("session_id")

        if not message:
            return JsonResponse({"success": False, "error": "Message required"})

        agent = ChatbotAgent()
        result = agent.process(message, request.user, session_id)
        
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def chat_history(request):
    """Lấy lịch sử chat"""
    from .agents.chatbot_agent import ChatbotAgent
    
    agent = ChatbotAgent()
    history = agent.get_history(request.user)
    
    return JsonResponse({"success": True, "data": history})

