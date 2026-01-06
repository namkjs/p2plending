"""
Agent Payment Monitor: Giám sát thanh toán với tools
- Kiểm tra lịch thanh toán
- Xử lý thanh toán
- Phát hiện trả chậm
- Tính phí phạt
"""

import time
import json
from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from langchain_core.tools import tool

from .base import BaseAgent
from ai_agents.tools.sql_tools import get_loan_detail, get_user_balance


# ================= PAYMENT TOOLS =================


@tool("get_payment_schedule")
def get_payment_schedule(contract_id: int) -> str:
    """
    Lấy lịch thanh toán của hợp đồng.

    Args:
        contract_id: ID hợp đồng

    Returns:
        JSON lịch thanh toán
    """
    from lending.models import LoanContract, PaymentSchedule

    try:
        contract = LoanContract.objects.get(id=contract_id)
        schedules = PaymentSchedule.objects.filter(contract=contract).order_by(
            "installment_number"
        )

        schedule_list = []
        total_paid = 0
        total_remaining = 0

        for s in schedules:
            is_overdue = s.due_date < datetime.now().date() and s.status == "PENDING"
            schedule_list.append(
                {
                    "id": s.id,
                    "installment": s.installment_number,
                    "due_date": str(s.due_date),
                    "principal": float(s.principal_amount),
                    "interest": float(s.interest_amount),
                    "total": float(s.total_amount),
                    "paid_amount": float(s.paid_amount or 0),
                    "status": s.status,
                    "is_overdue": is_overdue,
                    "late_days": (
                        (datetime.now().date() - s.due_date).days if is_overdue else 0
                    ),
                }
            )

            if s.status == "PAID":
                total_paid += float(s.paid_amount or s.total_amount)
            else:
                total_remaining += float(s.total_amount)

        return json.dumps(
            {
                "success": True,
                "data": {
                    "contract_id": contract_id,
                    "contract_number": contract.contract_number,
                    "total_installments": len(schedule_list),
                    "total_paid": total_paid,
                    "total_remaining": total_remaining,
                    "schedules": schedule_list,
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


@tool("get_pending_payments")
def get_pending_payments(user_id: int, role: str = "borrower") -> str:
    """
    Lấy các khoản thanh toán đang chờ của user.

    Args:
        user_id: ID user
        role: 'borrower' hoặc 'lender'

    Returns:
        JSON danh sách thanh toán
    """
    from lending.models import LoanContract, PaymentSchedule
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)

        if role == "borrower":
            contracts = LoanContract.objects.filter(borrower=user, is_active=True)
        else:
            contracts = LoanContract.objects.filter(lender=user, is_active=True)

        pending_list = []

        for contract in contracts:
            pending = (
                PaymentSchedule.objects.filter(contract=contract, status="PENDING")
                .order_by("due_date")
                .first()
            )

            if pending:
                is_overdue = pending.due_date < datetime.now().date()
                late_fee = 0

                if is_overdue:
                    late_days = (datetime.now().date() - pending.due_date).days
                    late_fee = (
                        float(pending.total_amount) * 0.0005 * late_days
                    )  # 0.05%/ngày

                pending_list.append(
                    {
                        "contract_id": contract.id,
                        "contract_number": contract.contract_number,
                        "payment_id": pending.id,
                        "installment": pending.installment_number,
                        "due_date": str(pending.due_date),
                        "amount": float(pending.total_amount),
                        "late_fee": round(late_fee, 0),
                        "total_due": float(pending.total_amount) + late_fee,
                        "is_overdue": is_overdue,
                        "late_days": (
                            (datetime.now().date() - pending.due_date).days
                            if is_overdue
                            else 0
                        ),
                        "other_party": (
                            contract.lender.username
                            if role == "borrower"
                            else contract.borrower.username
                        ),
                    }
                )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "user_id": user_id,
                    "role": role,
                    "pending_count": len(pending_list),
                    "total_amount_due": sum(p["total_due"] for p in pending_list),
                    "payments": pending_list,
                },
            },
            ensure_ascii=False,
        )

    except User.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy user ID {user_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("get_overdue_payments")
def get_overdue_payments(days_threshold: int = 0) -> str:
    """
    Lấy tất cả các khoản thanh toán quá hạn.

    Args:
        days_threshold: Số ngày quá hạn tối thiểu (0 = tất cả)

    Returns:
        JSON danh sách thanh toán quá hạn
    """
    from lending.models import PaymentSchedule

    try:
        threshold_date = datetime.now().date() - timedelta(days=days_threshold)

        overdue = PaymentSchedule.objects.filter(
            status="PENDING", due_date__lt=threshold_date, contract__is_active=True
        ).select_related("contract", "contract__borrower", "contract__lender")

        overdue_list = []
        total_overdue = 0

        for p in overdue:
            late_days = (datetime.now().date() - p.due_date).days
            late_fee = float(p.total_amount) * 0.0005 * late_days

            overdue_list.append(
                {
                    "payment_id": p.id,
                    "contract_id": p.contract.id,
                    "contract_number": p.contract.contract_number,
                    "borrower": p.contract.borrower.username,
                    "borrower_id": p.contract.borrower.id,
                    "lender": p.contract.lender.username,
                    "lender_id": p.contract.lender.id,
                    "installment": p.installment_number,
                    "due_date": str(p.due_date),
                    "amount": float(p.total_amount),
                    "late_days": late_days,
                    "late_fee": round(late_fee, 0),
                    "total_due": float(p.total_amount) + late_fee,
                }
            )
            total_overdue += float(p.total_amount) + late_fee

        return json.dumps(
            {
                "success": True,
                "data": {
                    "threshold_days": days_threshold,
                    "overdue_count": len(overdue_list),
                    "total_overdue_amount": total_overdue,
                    "payments": overdue_list,
                },
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("process_payment")
def process_payment(
    payment_id: int, user_id: int, amount: float, payment_method: str = "WALLET"
) -> str:
    """
    Xử lý thanh toán kỳ hạn.

    Args:
        payment_id: ID PaymentSchedule
        user_id: ID người thanh toán
        amount: Số tiền thanh toán
        payment_method: Phương thức (WALLET, BANK_TRANSFER)

    Returns:
        Kết quả thanh toán
    """
    from lending.models import PaymentSchedule, PaymentTransaction
    from user.models import UserProfile
    from django.contrib.auth.models import User
    from django.db import transaction as db_transaction

    try:
        with db_transaction.atomic():
            payment = PaymentSchedule.objects.select_for_update().get(id=payment_id)
            user = User.objects.get(id=user_id)

            # Verify user is borrower
            if payment.contract.borrower.id != user_id:
                return json.dumps(
                    {
                        "success": False,
                        "error": "Bạn không phải người vay trong hợp đồng này",
                    }
                )

            # Calculate late fee if any
            late_fee = 0
            late_days = 0
            if payment.due_date < datetime.now().date():
                late_days = (datetime.now().date() - payment.due_date).days
                late_fee = float(payment.total_amount) * 0.0005 * late_days

            total_due = float(payment.total_amount) + late_fee

            if amount < total_due:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Số tiền thanh toán ({amount:,.0f}) không đủ. Cần thanh toán: {total_due:,.0f} VNĐ",
                    }
                )

            # Check wallet balance if using wallet
            borrower_profile = UserProfile.objects.get(user=user)
            lender_profile = UserProfile.objects.get(user=payment.contract.lender)

            if payment_method == "WALLET":
                if float(borrower_profile.wallet_balance or 0) < total_due:
                    return json.dumps(
                        {
                            "success": False,
                            "error": f"Số dư ví không đủ. Số dư: {borrower_profile.wallet_balance:,.0f} VNĐ",
                        }
                    )

                # Deduct from borrower
                borrower_profile.wallet_balance = (
                    float(borrower_profile.wallet_balance or 0) - total_due
                )
                borrower_profile.save()

                # Add to lender
                lender_profile.wallet_balance = float(
                    lender_profile.wallet_balance or 0
                ) + float(payment.total_amount)
                lender_profile.save()

            # Create transaction record
            transaction = PaymentTransaction.objects.create(
                contract=payment.contract,
                payment_schedule=payment,
                payer=user,
                recipient=payment.contract.lender,
                amount=total_due,
                transaction_type="INSTALLMENT",
                payment_method=payment_method,
                status="COMPLETED",
                late_fee=late_fee,
                late_days=late_days,
            )

            # Update payment schedule
            payment.paid_amount = total_due
            payment.paid_date = datetime.now().date()
            payment.status = "PAID"
            payment.late_fee = late_fee
            payment.late_days = late_days
            payment.save()

            # Check if all payments done
            pending_count = PaymentSchedule.objects.filter(
                contract=payment.contract, status="PENDING"
            ).count()

            if pending_count == 0:
                payment.contract.status = "COMPLETED"
                payment.contract.is_active = False
                payment.contract.save()

                # Update loan request
                payment.contract.loan_request.status = "COMPLETED"
                payment.contract.loan_request.save()

            return json.dumps(
                {
                    "success": True,
                    "data": {
                        "transaction_id": transaction.id,
                        "amount_paid": total_due,
                        "principal": float(payment.principal_amount),
                        "interest": float(payment.interest_amount),
                        "late_fee": late_fee,
                        "late_days": late_days,
                        "payment_status": payment.status,
                        "contract_status": payment.contract.status,
                        "remaining_installments": pending_count,
                    },
                },
                ensure_ascii=False,
            )

    except PaymentSchedule.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy kỳ thanh toán ID {payment_id}"}
        )
    except User.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy user ID {user_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("calculate_early_payoff")
def calculate_early_payoff(contract_id: int) -> str:
    """
    Tính số tiền trả nợ trước hạn.

    Args:
        contract_id: ID hợp đồng

    Returns:
        JSON thông tin trả trước hạn
    """
    from lending.models import LoanContract, PaymentSchedule

    try:
        contract = LoanContract.objects.get(id=contract_id)

        # Get remaining payments
        pending = PaymentSchedule.objects.filter(
            contract=contract, status="PENDING"
        ).order_by("installment_number")

        total_principal = sum(float(p.principal_amount) for p in pending)
        total_interest = sum(float(p.interest_amount) for p in pending)

        # Discount: chỉ tính 50% lãi còn lại
        discounted_interest = total_interest * 0.5

        # Calculate any late fees
        late_fee = 0
        for p in pending:
            if p.due_date < datetime.now().date():
                days = (datetime.now().date() - p.due_date).days
                late_fee += float(p.total_amount) * 0.0005 * days

        total_payoff = total_principal + discounted_interest + late_fee
        savings = total_interest - discounted_interest

        return json.dumps(
            {
                "success": True,
                "data": {
                    "contract_id": contract_id,
                    "remaining_installments": pending.count(),
                    "total_principal_remaining": total_principal,
                    "total_interest_remaining": total_interest,
                    "interest_discount": savings,
                    "discounted_interest": discounted_interest,
                    "late_fees": late_fee,
                    "total_payoff_amount": total_payoff,
                    "savings": savings,
                    "note": "Trả trước hạn được giảm 50% lãi còn lại",
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


@tool("send_payment_reminder")
def send_payment_reminder(payment_id: int) -> str:
    """
    Gửi nhắc nhở thanh toán.

    Args:
        payment_id: ID PaymentSchedule

    Returns:
        Kết quả gửi nhắc nhở
    """
    from lending.models import PaymentSchedule
    from ai_agents.models import Notification

    try:
        payment = PaymentSchedule.objects.get(id=payment_id)

        is_overdue = payment.due_date < datetime.now().date()

        if is_overdue:
            late_days = (datetime.now().date() - payment.due_date).days
            late_fee = float(payment.total_amount) * 0.0005 * late_days

            title = f"⚠️ Khoản thanh toán quá hạn {late_days} ngày!"
            message = f"""Hợp đồng {payment.contract.contract_number}
Kỳ {payment.installment_number}: {float(payment.total_amount):,.0f} VNĐ
Phí trễ hạn: {late_fee:,.0f} VNĐ
Tổng cần thanh toán: {float(payment.total_amount) + late_fee:,.0f} VNĐ
Vui lòng thanh toán ngay để tránh phí phạt tăng thêm!"""
            notification_type = "PAYMENT_OVERDUE"
        else:
            days_until = (payment.due_date - datetime.now().date()).days
            title = f"📅 Nhắc nhở thanh toán (còn {days_until} ngày)"
            message = f"""Hợp đồng {payment.contract.contract_number}
Kỳ {payment.installment_number}: {float(payment.total_amount):,.0f} VNĐ
Ngày đến hạn: {payment.due_date.strftime('%d/%m/%Y')}
Vui lòng chuẩn bị thanh toán đúng hạn."""
            notification_type = "PAYMENT_REMINDER"

        Notification.objects.create(
            user=payment.contract.borrower,
            notification_type=notification_type,
            title=title,
            message=message,
            related_loan=payment.contract.loan_request,
        )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "sent_to": payment.contract.borrower.username,
                    "payment_id": payment_id,
                    "is_overdue": is_overdue,
                    "notification_type": notification_type,
                },
            },
            ensure_ascii=False,
        )

    except PaymentSchedule.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy kỳ thanh toán ID {payment_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ================= AGENT CLASS =================


class PaymentMonitorAgent(BaseAgent):
    """Agent giám sát thanh toán với tools"""

    agent_type = "PAYMENT_MONITOR"

    system_prompt = """Bạn là Payment Monitor Agent cho nền tảng P2P Lending.

Nhiệm vụ của bạn:
1. Giám sát lịch thanh toán của tất cả hợp đồng
2. Phát hiện các khoản thanh toán sắp đến hạn và quá hạn
3. Gửi nhắc nhở thanh toán
4. Xử lý thanh toán kỳ hạn
5. Tính toán trả nợ trước hạn

Bạn có thể sử dụng các công cụ sau:
- get_payment_schedule: Lấy lịch thanh toán của hợp đồng
- get_pending_payments: Lấy các khoản đang chờ thanh toán
- get_overdue_payments: Lấy các khoản quá hạn
- process_payment: Xử lý thanh toán
- calculate_early_payoff: Tính trả nợ trước hạn
- send_payment_reminder: Gửi nhắc nhở
- get_user_balance: Kiểm tra số dư

Quy tắc:
- Phí trễ hạn: 0.05%/ngày trên số tiền trả chậm
- Trả trước hạn: Giảm 50% lãi còn lại
- Ưu tiên thanh toán từ ví điện tử

Hãy giám sát và xử lý thanh toán chính xác."""

    tools = [
        get_payment_schedule,
        get_pending_payments,
        get_overdue_payments,
        process_payment,
        calculate_early_payoff,
        send_payment_reminder,
        get_loan_detail,
        get_user_balance,
    ]

    def process(self, contract=None, action: str = "monitor") -> Dict[str, Any]:
        """
        Xử lý giám sát thanh toán

        Args:
            contract: LoanContract object (optional)
            action: 'monitor', 'remind', 'report'

        Returns:
            Dict với kết quả xử lý
        """
        start_time = time.time()

        input_data = {
            "contract_id": contract.id if contract else None,
            "action": action,
        }

        log = self._log_start(contract.borrower if contract else None, input_data)

        try:
            if action == "monitor":
                result = self._monitor_all_payments()
            elif action == "remind" and contract:
                result = self._send_reminders(contract)
            elif action == "report":
                result = self._generate_report()
            else:
                result = {"message": "Invalid action"}

            self._log_success(log, result, start_time)
            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _monitor_all_payments(self) -> Dict:
        """Giám sát tất cả thanh toán"""
        # Get overdue payments
        overdue_result = get_overdue_payments.invoke(0)
        overdue_data = json.loads(overdue_result)

        # Send reminders for overdue
        reminders_sent = 0
        if overdue_data.get("success"):
            for payment in overdue_data["data"]["payments"][:10]:  # Limit 10
                send_payment_reminder.invoke(payment["payment_id"])
                reminders_sent += 1

        # Get upcoming payments (next 3 days)
        from lending.models import PaymentSchedule

        upcoming_date = datetime.now().date() + timedelta(days=3)
        upcoming = PaymentSchedule.objects.filter(
            status="PENDING",
            due_date__lte=upcoming_date,
            due_date__gte=datetime.now().date(),
            contract__is_active=True,
        ).count()

        return {
            "overdue_count": (
                overdue_data["data"]["overdue_count"]
                if overdue_data.get("success")
                else 0
            ),
            "total_overdue_amount": (
                overdue_data["data"]["total_overdue_amount"]
                if overdue_data.get("success")
                else 0
            ),
            "reminders_sent": reminders_sent,
            "upcoming_payments": upcoming,
            "monitored_at": datetime.now().isoformat(),
        }

    def _send_reminders(self, contract) -> Dict:
        """Gửi nhắc nhở cho contract cụ thể"""
        schedule_result = get_payment_schedule.invoke(contract.id)
        schedule_data = json.loads(schedule_result)

        reminders_sent = 0

        if schedule_data.get("success"):
            for payment in schedule_data["data"]["schedules"]:
                if payment["status"] == "PENDING":
                    send_payment_reminder.invoke(payment["id"])
                    reminders_sent += 1
                    break  # Only send for next payment

        return {
            "contract_id": contract.id,
            "reminders_sent": reminders_sent,
        }

    def _generate_report(self) -> Dict:
        """Tạo báo cáo thanh toán tổng hợp"""
        from lending.models import PaymentSchedule, PaymentTransaction
        from datetime import timedelta

        # Summary statistics
        today = datetime.now().date()
        this_month_start = today.replace(day=1)

        total_pending = PaymentSchedule.objects.filter(status="PENDING").count()
        total_overdue = PaymentSchedule.objects.filter(
            status="PENDING", due_date__lt=today
        ).count()

        # This month's payments
        month_paid = PaymentTransaction.objects.filter(
            status="COMPLETED", created_at__gte=this_month_start
        )

        total_collected = sum(float(t.amount) for t in month_paid)
        total_late_fees = sum(float(t.late_fee or 0) for t in month_paid)

        return {
            "report_date": str(today),
            "total_pending_payments": total_pending,
            "total_overdue_payments": total_overdue,
            "month_payments_collected": month_paid.count(),
            "month_amount_collected": total_collected,
            "month_late_fees_collected": total_late_fees,
        }

    def make_payment(self, user, payment_id: int, amount: float = None) -> Dict:
        """
        API để user thanh toán

        Args:
            user: User thanh toán
            payment_id: ID kỳ thanh toán
            amount: Số tiền (optional, nếu không truyền sẽ thanh toán đủ)
        """
        from lending.models import PaymentSchedule

        try:
            payment = PaymentSchedule.objects.get(id=payment_id)

            # Calculate total due
            late_fee = 0
            if payment.due_date < datetime.now().date():
                late_days = (datetime.now().date() - payment.due_date).days
                late_fee = float(payment.total_amount) * 0.0005 * late_days

            total_due = float(payment.total_amount) + late_fee

            if amount is None:
                amount = total_due

            # Process payment
            result = process_payment.invoke(payment_id, user.id, amount, "WALLET")
            result_data = json.loads(result)

            if result_data.get("success"):
                # Notify lender
                self._create_notification(
                    user=payment.contract.lender,
                    notification_type="PAYMENT_RECEIVED",
                    title="💰 Đã nhận thanh toán",
                    message=f"""Khoản thanh toán từ {payment.contract.borrower.username}
Hợp đồng: {payment.contract.contract_number}
Kỳ {payment.installment_number}: {amount:,.0f} VNĐ
Đã được chuyển vào ví của bạn.""",
                    related_loan_id=payment.contract.loan_request.id,
                )

            return result_data

        except Exception as e:
            return {"success": False, "error": str(e)}

    def early_payoff(self, user, contract_id: int) -> Dict:
        """
        Trả nợ trước hạn

        Args:
            user: User trả nợ
            contract_id: ID hợp đồng
        """
        from lending.models import LoanContract, PaymentSchedule, PaymentTransaction
        from user.models import UserProfile
        from django.db import transaction as db_transaction

        try:
            # Calculate early payoff
            calc_result = calculate_early_payoff.invoke(contract_id)
            calc_data = json.loads(calc_result)

            if not calc_data.get("success"):
                return calc_data

            payoff_amount = calc_data["data"]["total_payoff_amount"]
            savings = calc_data["data"]["savings"]

            with db_transaction.atomic():
                contract = LoanContract.objects.select_for_update().get(id=contract_id)

                if contract.borrower != user:
                    return {
                        "success": False,
                        "error": "Bạn không phải người vay trong hợp đồng này",
                    }

                # Check balance
                borrower_profile = UserProfile.objects.get(user=user)
                if float(borrower_profile.wallet_balance or 0) < payoff_amount:
                    return {
                        "success": False,
                        "error": f"Số dư ví không đủ. Cần: {payoff_amount:,.0f} VNĐ",
                    }

                # Process payment
                borrower_profile.wallet_balance = (
                    float(borrower_profile.wallet_balance) - payoff_amount
                )
                borrower_profile.save()

                lender_profile = UserProfile.objects.get(user=contract.lender)
                lender_profile.wallet_balance = (
                    float(lender_profile.wallet_balance or 0) + payoff_amount
                )
                lender_profile.save()

                # Mark all pending as paid
                PaymentSchedule.objects.filter(
                    contract=contract, status="PENDING"
                ).update(
                    status="PAID", paid_date=datetime.now().date(), note="Early payoff"
                )

                # Create transaction
                PaymentTransaction.objects.create(
                    contract=contract,
                    payer=user,
                    recipient=contract.lender,
                    amount=payoff_amount,
                    transaction_type="EARLY_PAYOFF",
                    payment_method="WALLET",
                    status="COMPLETED",
                )

                # Close contract
                contract.status = "COMPLETED"
                contract.is_active = False
                contract.save()

                contract.loan_request.status = "COMPLETED"
                contract.loan_request.save()

            # Notify
            self._create_notification(
                user=contract.lender,
                notification_type="PAYMENT_RECEIVED",
                title="💰 Đã nhận thanh toán trước hạn",
                message=f"""{contract.borrower.username} đã trả nợ trước hạn.
Hợp đồng: {contract.contract_number}
Số tiền: {payoff_amount:,.0f} VNĐ
Hợp đồng đã hoàn tất.""",
                related_loan_id=contract.loan_request.id,
            )

            return {
                "success": True,
                "data": {
                    "amount_paid": payoff_amount,
                    "savings": savings,
                    "contract_status": "COMPLETED",
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
