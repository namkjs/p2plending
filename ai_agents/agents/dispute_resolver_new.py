"""
Agent Dispute Resolver: Giải quyết tranh chấp với tools
- Phân tích tranh chấp
- Thu thập bằng chứng
- Đề xuất giải pháp
- Xử lý hoàn tiền/phạt
"""

import time
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from langchain_core.tools import tool

from .base import BaseAgent
from ai_agents.tools.sql_tools import get_loan_detail, get_user_balance


# ================= DISPUTE TOOLS =================


@tool("create_dispute")
def create_dispute(
    contract_id: int, complainant_id: int, dispute_type: str, description: str
) -> str:
    """
    Tạo tranh chấp mới.

    Args:
        contract_id: ID hợp đồng
        complainant_id: ID người khiếu nại
        dispute_type: Loại tranh chấp (PAYMENT, CONTRACT_TERMS, FRAUD, OTHER)
        description: Mô tả chi tiết

    Returns:
        JSON thông tin tranh chấp
    """
    from lending.models import LoanContract, Dispute
    from django.contrib.auth.models import User

    try:
        contract = LoanContract.objects.get(id=contract_id)
        complainant = User.objects.get(id=complainant_id)

        # Determine respondent
        if complainant == contract.borrower:
            respondent = contract.lender
        else:
            respondent = contract.borrower

        dispute = Dispute.objects.create(
            contract=contract,
            complainant=complainant,
            respondent=respondent,
            dispute_type=dispute_type,
            description=description,
            status="OPEN",
        )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "dispute_id": dispute.id,
                    "contract_id": contract_id,
                    "complainant": complainant.username,
                    "respondent": respondent.username,
                    "dispute_type": dispute_type,
                    "status": "OPEN",
                    "created_at": dispute.created_at.isoformat(),
                },
            },
            ensure_ascii=False,
        )

    except LoanContract.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy hợp đồng ID {contract_id}"}
        )
    except User.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy user ID {complainant_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("get_dispute_details")
def get_dispute_details(dispute_id: int) -> str:
    """
    Lấy chi tiết tranh chấp.

    Args:
        dispute_id: ID tranh chấp

    Returns:
        JSON chi tiết tranh chấp
    """
    from lending.models import Dispute, DisputeEvidence

    try:
        dispute = Dispute.objects.select_related(
            "contract", "complainant", "respondent"
        ).get(id=dispute_id)

        # Get evidence
        evidence_list = DisputeEvidence.objects.filter(dispute=dispute)
        evidence_data = [
            {
                "id": e.id,
                "submitted_by": e.submitted_by.username,
                "evidence_type": e.evidence_type,
                "description": e.description,
                "file_url": e.file.url if e.file else None,
                "submitted_at": e.created_at.isoformat(),
            }
            for e in evidence_list
        ]

        return json.dumps(
            {
                "success": True,
                "data": {
                    "dispute_id": dispute.id,
                    "contract_id": dispute.contract.id,
                    "contract_number": dispute.contract.contract_number,
                    "complainant": {
                        "id": dispute.complainant.id,
                        "username": dispute.complainant.username,
                    },
                    "respondent": {
                        "id": dispute.respondent.id,
                        "username": dispute.respondent.username,
                    },
                    "dispute_type": dispute.dispute_type,
                    "description": dispute.description,
                    "status": dispute.status,
                    "resolution": dispute.resolution,
                    "evidence": evidence_data,
                    "created_at": dispute.created_at.isoformat(),
                    "updated_at": (
                        dispute.updated_at.isoformat() if dispute.updated_at else None
                    ),
                },
            },
            ensure_ascii=False,
        )

    except Dispute.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy tranh chấp ID {dispute_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("get_contract_history")
def get_contract_history(contract_id: int) -> str:
    """
    Lấy lịch sử giao dịch của hợp đồng.

    Args:
        contract_id: ID hợp đồng

    Returns:
        JSON lịch sử giao dịch
    """
    from lending.models import LoanContract, PaymentSchedule, PaymentTransaction

    try:
        contract = LoanContract.objects.get(id=contract_id)

        # Payment history
        payments = PaymentSchedule.objects.filter(contract=contract).order_by(
            "installment_number"
        )
        payment_data = [
            {
                "installment": p.installment_number,
                "due_date": str(p.due_date),
                "amount": float(p.total_amount),
                "paid_amount": float(p.paid_amount or 0),
                "paid_date": str(p.paid_date) if p.paid_date else None,
                "status": p.status,
                "late_days": p.late_days or 0,
            }
            for p in payments
        ]

        # Transaction history
        transactions = PaymentTransaction.objects.filter(contract=contract).order_by(
            "-created_at"
        )
        transaction_data = [
            {
                "id": t.id,
                "type": t.transaction_type,
                "amount": float(t.amount),
                "payer": t.payer.username,
                "recipient": t.recipient.username,
                "status": t.status,
                "date": t.created_at.isoformat(),
            }
            for t in transactions
        ]

        # Calculate statistics
        total_paid = sum(
            float(p.paid_amount or 0) for p in payments if p.status == "PAID"
        )
        total_remaining = sum(
            float(p.total_amount) for p in payments if p.status == "PENDING"
        )
        on_time_payments = payments.filter(late_days=0, status="PAID").count()
        late_payments = payments.filter(late_days__gt=0, status="PAID").count()

        return json.dumps(
            {
                "success": True,
                "data": {
                    "contract_id": contract_id,
                    "contract_number": contract.contract_number,
                    "borrower": contract.borrower.username,
                    "lender": contract.lender.username,
                    "principal": float(contract.principal_amount),
                    "status": contract.status,
                    "start_date": str(contract.start_date),
                    "end_date": str(contract.end_date),
                    "statistics": {
                        "total_paid": total_paid,
                        "total_remaining": total_remaining,
                        "on_time_payments": on_time_payments,
                        "late_payments": late_payments,
                        "payment_rate": f"{on_time_payments / max(1, on_time_payments + late_payments) * 100:.1f}%",
                    },
                    "payments": payment_data,
                    "transactions": transaction_data,
                },
            },
            ensure_ascii=False,
        )

    except LoanContract.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy hợp đồng ID {contract_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("add_dispute_evidence")
def add_dispute_evidence(
    dispute_id: int, user_id: int, evidence_type: str, description: str
) -> str:
    """
    Thêm bằng chứng cho tranh chấp.

    Args:
        dispute_id: ID tranh chấp
        user_id: ID người submit
        evidence_type: Loại (SCREENSHOT, DOCUMENT, CHAT_LOG, OTHER)
        description: Mô tả bằng chứng

    Returns:
        Kết quả thêm bằng chứng
    """
    from lending.models import Dispute, DisputeEvidence
    from django.contrib.auth.models import User

    try:
        dispute = Dispute.objects.get(id=dispute_id)
        user = User.objects.get(id=user_id)

        # Verify user is party to dispute
        if user not in [dispute.complainant, dispute.respondent]:
            return json.dumps(
                {
                    "success": False,
                    "error": "Bạn không phải bên liên quan trong tranh chấp này",
                }
            )

        if dispute.status in ["RESOLVED", "CLOSED"]:
            return json.dumps(
                {
                    "success": False,
                    "error": "Tranh chấp đã đóng, không thể thêm bằng chứng",
                }
            )

        evidence = DisputeEvidence.objects.create(
            dispute=dispute,
            submitted_by=user,
            evidence_type=evidence_type,
            description=description,
        )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "evidence_id": evidence.id,
                    "dispute_id": dispute_id,
                    "submitted_by": user.username,
                    "evidence_type": evidence_type,
                    "description": description,
                },
            },
            ensure_ascii=False,
        )

    except Dispute.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy tranh chấp ID {dispute_id}"}
        )
    except User.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy user ID {user_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("analyze_dispute")
def analyze_dispute(dispute_id: int) -> str:
    """
    Phân tích tranh chấp và đề xuất giải pháp.

    Args:
        dispute_id: ID tranh chấp

    Returns:
        JSON phân tích và đề xuất
    """
    from lending.models import Dispute, PaymentSchedule

    try:
        dispute = Dispute.objects.select_related("contract").get(id=dispute_id)
        contract = dispute.contract

        # Get payment history
        payments = PaymentSchedule.objects.filter(contract=contract)
        paid_count = payments.filter(status="PAID").count()
        total_count = payments.count()
        late_count = payments.filter(late_days__gt=0).count()

        # Analyze based on dispute type
        analysis = {
            "dispute_type": dispute.dispute_type,
            "severity": "MEDIUM",
            "recommendations": [],
            "factors": {},
        }

        if dispute.dispute_type == "PAYMENT":
            # Payment dispute analysis
            overdue = payments.filter(
                status="PENDING", due_date__lt=datetime.now().date()
            )
            total_overdue = sum(float(p.total_amount) for p in overdue)

            analysis["factors"] = {
                "payments_made": f"{paid_count}/{total_count}",
                "late_payments": late_count,
                "overdue_amount": total_overdue,
            }

            if paid_count == 0:
                analysis["severity"] = "HIGH"
                analysis["recommendations"] = [
                    "Người vay chưa thực hiện thanh toán nào",
                    "Đề xuất: Yêu cầu thanh toán ngay hoặc hủy hợp đồng",
                    "Xem xét hoàn tiền cho người cho vay",
                ]
            elif late_count > total_count * 0.5:
                analysis["severity"] = "HIGH"
                analysis["recommendations"] = [
                    "Hơn 50% các kỳ thanh toán bị trễ",
                    "Đề xuất: Điều chỉnh lịch thanh toán hoặc tăng phí trễ hạn",
                ]
            else:
                analysis["severity"] = "LOW"
                analysis["recommendations"] = [
                    "Lịch sử thanh toán tương đối tốt",
                    "Đề xuất: Hòa giải và nhắc nhở thanh toán đúng hạn",
                ]

        elif dispute.dispute_type == "FRAUD":
            analysis["severity"] = "CRITICAL"
            analysis["recommendations"] = [
                "Tranh chấp liên quan đến gian lận - cần xác minh ngay",
                "Thu thập thêm bằng chứng từ cả hai bên",
                "Tạm đóng băng hợp đồng",
                "Xem xét hoàn tiền nếu xác nhận gian lận",
            ]

        elif dispute.dispute_type == "CONTRACT_TERMS":
            analysis["severity"] = "MEDIUM"
            analysis["recommendations"] = [
                "Xem xét lại các điều khoản hợp đồng",
                "Đề xuất điều chỉnh theo thỏa thuận của hai bên",
                "Cập nhật hợp đồng nếu cần",
            ]

        else:
            analysis["recommendations"] = [
                "Thu thập thêm thông tin từ cả hai bên",
                "Xem xét hòa giải",
            ]

        return json.dumps(
            {
                "success": True,
                "data": {
                    "dispute_id": dispute_id,
                    "contract_id": contract.id,
                    "analysis": analysis,
                },
            },
            ensure_ascii=False,
        )

    except Dispute.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy tranh chấp ID {dispute_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("resolve_dispute")
def resolve_dispute(
    dispute_id: int,
    resolution_type: str,
    resolution_note: str,
    refund_amount: float = 0,
    penalty_amount: float = 0,
    penalized_user_id: int = None,
) -> str:
    """
    Giải quyết tranh chấp.

    Args:
        dispute_id: ID tranh chấp
        resolution_type: Loại giải quyết (FAVOR_COMPLAINANT, FAVOR_RESPONDENT, COMPROMISE, DISMISSED)
        resolution_note: Ghi chú giải quyết
        refund_amount: Số tiền hoàn (nếu có)
        penalty_amount: Số tiền phạt (nếu có)
        penalized_user_id: ID user bị phạt (nếu có)

    Returns:
        Kết quả giải quyết
    """
    from lending.models import Dispute
    from user.models import UserProfile
    from django.contrib.auth.models import User
    from django.db import transaction as db_transaction

    try:
        with db_transaction.atomic():
            dispute = Dispute.objects.select_for_update().get(id=dispute_id)

            if dispute.status in ["RESOLVED", "CLOSED"]:
                return json.dumps(
                    {"success": False, "error": "Tranh chấp đã được giải quyết"}
                )

            # Process refund if any
            if refund_amount > 0:
                if resolution_type == "FAVOR_COMPLAINANT":
                    # Refund to complainant from respondent
                    respondent_profile = UserProfile.objects.get(
                        user=dispute.respondent
                    )
                    complainant_profile = UserProfile.objects.get(
                        user=dispute.complainant
                    )

                    if float(respondent_profile.wallet_balance or 0) >= refund_amount:
                        respondent_profile.wallet_balance = (
                            float(respondent_profile.wallet_balance) - refund_amount
                        )
                        respondent_profile.save()

                        complainant_profile.wallet_balance = (
                            float(complainant_profile.wallet_balance or 0)
                            + refund_amount
                        )
                        complainant_profile.save()
                    else:
                        return json.dumps(
                            {
                                "success": False,
                                "error": "Số dư bên bị phạt không đủ để hoàn tiền",
                            }
                        )

            # Process penalty if any
            if penalty_amount > 0 and penalized_user_id:
                penalized_user = User.objects.get(id=penalized_user_id)
                penalized_profile = UserProfile.objects.get(user=penalized_user)

                if float(penalized_profile.wallet_balance or 0) >= penalty_amount:
                    penalized_profile.wallet_balance = (
                        float(penalized_profile.wallet_balance) - penalty_amount
                    )
                    penalized_profile.save()
                    # Penalty goes to platform (not implemented yet)

            # Update dispute
            dispute.status = "RESOLVED"
            dispute.resolution = resolution_note
            dispute.resolution_type = resolution_type
            dispute.refund_amount = refund_amount
            dispute.penalty_amount = penalty_amount
            dispute.resolved_at = datetime.now()
            dispute.save()

            return json.dumps(
                {
                    "success": True,
                    "data": {
                        "dispute_id": dispute_id,
                        "resolution_type": resolution_type,
                        "resolution_note": resolution_note,
                        "refund_amount": refund_amount,
                        "penalty_amount": penalty_amount,
                        "status": "RESOLVED",
                    },
                },
                ensure_ascii=False,
            )

    except Dispute.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy tranh chấp ID {dispute_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("get_open_disputes")
def get_open_disputes(user_id: int = None) -> str:
    """
    Lấy danh sách tranh chấp đang mở.

    Args:
        user_id: ID user (optional, lấy của user cụ thể)

    Returns:
        JSON danh sách tranh chấp
    """
    from lending.models import Dispute
    from django.db.models import Q

    try:
        queryset = Dispute.objects.filter(
            status__in=["OPEN", "IN_REVIEW"]
        ).select_related("contract", "complainant", "respondent")

        if user_id:
            queryset = queryset.filter(
                Q(complainant_id=user_id) | Q(respondent_id=user_id)
            )

        disputes = []
        for d in queryset.order_by("-created_at"):
            disputes.append(
                {
                    "id": d.id,
                    "contract_number": d.contract.contract_number,
                    "complainant": d.complainant.username,
                    "respondent": d.respondent.username,
                    "dispute_type": d.dispute_type,
                    "status": d.status,
                    "created_at": d.created_at.isoformat(),
                    "days_open": (datetime.now() - d.created_at).days,
                }
            )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "count": len(disputes),
                    "disputes": disputes,
                },
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ================= AGENT CLASS =================


class DisputeResolverAgent(BaseAgent):
    """Agent giải quyết tranh chấp với tools"""

    agent_type = "DISPUTE_RESOLVER"

    system_prompt = """Bạn là Dispute Resolver Agent cho nền tảng P2P Lending.

Nhiệm vụ của bạn:
1. Tiếp nhận và xử lý tranh chấp giữa người vay và người cho vay
2. Thu thập và phân tích bằng chứng
3. Đưa ra phân tích khách quan
4. Đề xuất và thực hiện giải pháp công bằng

Quy trình xử lý tranh chấp:
1. Tiếp nhận tranh chấp và ghi nhận
2. Thu thập bằng chứng từ hai bên
3. Phân tích lịch sử giao dịch
4. Đánh giá mức độ nghiêm trọng
5. Đề xuất giải pháp
6. Thực hiện giải quyết (hoàn tiền/phạt nếu cần)

Bạn có thể sử dụng các công cụ sau:
- create_dispute: Tạo tranh chấp mới
- get_dispute_details: Lấy chi tiết tranh chấp
- get_contract_history: Lấy lịch sử giao dịch
- add_dispute_evidence: Thêm bằng chứng
- analyze_dispute: Phân tích và đề xuất
- resolve_dispute: Giải quyết tranh chấp
- get_open_disputes: Lấy tranh chấp đang mở

Nguyên tắc:
- Công bằng và khách quan
- Dựa trên bằng chứng
- Ưu tiên hòa giải
- Bảo vệ quyền lợi cả hai bên

Hãy xử lý tranh chấp một cách công bằng và chuyên nghiệp."""

    tools = [
        create_dispute,
        get_dispute_details,
        get_contract_history,
        add_dispute_evidence,
        analyze_dispute,
        resolve_dispute,
        get_open_disputes,
        get_loan_detail,
        get_user_balance,
    ]

    def process(self, dispute=None, action: str = "review") -> Dict[str, Any]:
        """
        Xử lý tranh chấp

        Args:
            dispute: Dispute object (optional)
            action: 'review', 'analyze', 'resolve'

        Returns:
            Dict với kết quả xử lý
        """
        start_time = time.time()

        input_data = {
            "dispute_id": dispute.id if dispute else None,
            "action": action,
        }

        log = self._log_start(dispute.complainant if dispute else None, input_data)

        try:
            if action == "analyze" and dispute:
                result = self._analyze_dispute(dispute)
            elif action == "resolve" and dispute:
                result = self._auto_resolve(dispute)
            else:
                result = self._review_open_disputes()

            self._log_success(log, result, start_time)
            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _analyze_dispute(self, dispute) -> Dict:
        """Phân tích tranh chấp"""
        # Get details
        details_result = get_dispute_details.invoke(dispute.id)
        details = json.loads(details_result)

        # Get contract history
        history_result = get_contract_history.invoke(dispute.contract.id)
        history = json.loads(history_result)

        # Analyze
        analysis_result = analyze_dispute.invoke(dispute.id)
        analysis = json.loads(analysis_result)

        return {
            "dispute": details.get("data", {}),
            "contract_history": history.get("data", {}),
            "analysis": analysis.get("data", {}).get("analysis", {}),
        }

    def _auto_resolve(self, dispute) -> Dict:
        """Tự động giải quyết tranh chấp đơn giản"""
        # Get analysis
        analysis_result = analyze_dispute.invoke(dispute.id)
        analysis_data = json.loads(analysis_result)

        if not analysis_data.get("success"):
            return {"error": "Cannot analyze dispute"}

        analysis = analysis_data["data"]["analysis"]
        severity = analysis.get("severity", "MEDIUM")

        # Auto resolve low severity disputes
        if severity == "LOW":
            resolution_type = "COMPROMISE"
            resolution_note = "Tranh chấp có mức độ thấp. Đề xuất hai bên tiếp tục thực hiện hợp đồng và tuân thủ các điều khoản."

            resolve_result = resolve_dispute.invoke(
                dispute.id,
                resolution_type,
                resolution_note,
                0,  # no refund
                0,  # no penalty
                None,
            )

            result_data = json.loads(resolve_result)

            if result_data.get("success"):
                # Notify both parties
                self._notify_resolution(dispute, resolution_type, resolution_note)

            return result_data.get("data", {})

        else:
            return {
                "message": "Tranh chấp cần xem xét thủ công",
                "severity": severity,
                "recommendations": analysis.get("recommendations", []),
            }

    def _review_open_disputes(self) -> Dict:
        """Review tất cả tranh chấp đang mở"""
        result = get_open_disputes.invoke(None)
        data = json.loads(result)

        if data.get("success"):
            disputes = data["data"]["disputes"]

            # Categorize by severity
            critical = []
            high = []
            other = []

            for d in disputes:
                if d["dispute_type"] == "FRAUD":
                    critical.append(d)
                elif d["days_open"] > 7:
                    high.append(d)
                else:
                    other.append(d)

            return {
                "total_open": len(disputes),
                "critical": critical,
                "high_priority": high,
                "normal": other,
            }

        return data

    def _notify_resolution(self, dispute, resolution_type, resolution_note):
        """Thông báo kết quả giải quyết"""
        resolution_titles = {
            "FAVOR_COMPLAINANT": "có lợi cho bạn",
            "FAVOR_RESPONDENT": "có lợi cho bên kia",
            "COMPROMISE": "thỏa thuận giữa hai bên",
            "DISMISSED": "bác bỏ",
        }

        title_text = resolution_titles.get(resolution_type, resolution_type)

        # Notify complainant
        self._create_notification(
            user=dispute.complainant,
            notification_type="DISPUTE_STATUS",
            title=f"⚖️ Tranh chấp đã được giải quyết ({title_text})",
            message=f"""Tranh chấp về hợp đồng {dispute.contract.contract_number} đã được giải quyết.

Kết quả: {resolution_note}

Nếu bạn không đồng ý với quyết định, vui lòng liên hệ hỗ trợ.""",
            related_loan_id=dispute.contract.loan_request.id,
        )

        # Notify respondent
        self._create_notification(
            user=dispute.respondent,
            notification_type="DISPUTE_STATUS",
            title=f"⚖️ Tranh chấp đã được giải quyết ({title_text})",
            message=f"""Tranh chấp về hợp đồng {dispute.contract.contract_number} đã được giải quyết.

Kết quả: {resolution_note}

Nếu bạn không đồng ý với quyết định, vui lòng liên hệ hỗ trợ.""",
            related_loan_id=dispute.contract.loan_request.id,
        )

    def file_dispute(
        self, user, contract_id: int, dispute_type: str, description: str
    ) -> Dict:
        """
        API để user tạo tranh chấp

        Args:
            user: User tạo tranh chấp
            contract_id: ID hợp đồng
            dispute_type: Loại tranh chấp
            description: Mô tả
        """
        from lending.models import LoanContract

        try:
            contract = LoanContract.objects.get(id=contract_id)

            # Verify user is party to contract
            if user not in [contract.borrower, contract.lender]:
                return {
                    "success": False,
                    "error": "Bạn không phải bên trong hợp đồng này",
                }

            # Create dispute
            result = create_dispute.invoke(
                contract_id, user.id, dispute_type, description
            )
            result_data = json.loads(result)

            if result_data.get("success"):
                # Notify the other party
                other_party = (
                    contract.lender if user == contract.borrower else contract.borrower
                )

                self._create_notification(
                    user=other_party,
                    notification_type="DISPUTE_STATUS",
                    title="⚠️ Có tranh chấp mới",
                    message=f"""{user.username} đã tạo tranh chấp về hợp đồng {contract.contract_number}.

Loại: {dispute_type}
Mô tả: {description[:100]}...

Vui lòng phản hồi và cung cấp bằng chứng.""",
                    related_loan_id=contract.loan_request.id,
                )

            return result_data

        except Exception as e:
            return {"success": False, "error": str(e)}

    def respond_to_dispute(
        self, user, dispute_id: int, response: str, evidence_type: str = None
    ) -> Dict:
        """
        Phản hồi tranh chấp

        Args:
            user: User phản hồi
            dispute_id: ID tranh chấp
            response: Nội dung phản hồi
            evidence_type: Loại bằng chứng (optional)
        """
        # Add evidence/response
        result = add_dispute_evidence.invoke(
            dispute_id, user.id, evidence_type or "OTHER", response
        )

        return json.loads(result)
