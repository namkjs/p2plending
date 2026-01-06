"""
Agent Payment Monitor: Theo dõi thanh toán, nhắc nhở
- Kiểm tra các khoản đến hạn
- Gửi nhắc nhở thanh toán
- Cập nhật trạng thái thanh toán
"""

import time
from typing import Any, Dict, List
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Q

from .base import BaseAgent


class PaymentMonitorAgent(BaseAgent):
    """Agent theo dõi thanh toán và nhắc nhở"""

    agent_type = "PAYMENT_MONITOR"

    SYSTEM_PROMPT = """Bạn là trợ lý tài chính cho nền tảng P2P Lending.
Nhiệm vụ: Tạo tin nhắn nhắc nhở thanh toán thân thiện nhưng chuyên nghiệp.

Các loại tin nhắn:
1. Nhắc trước hạn (3-7 ngày): Nhẹ nhàng, thông báo
2. Nhắc đúng hạn: Nhấn mạnh deadline
3. Nhắc quá hạn: Nghiêm túc, cảnh báo hậu quả

Trả về JSON với format:
{
    "message_type": "<REMINDER|WARNING|URGENT>",
    "title": "tiêu đề ngắn gọn",
    "message": "nội dung tin nhắn đầy đủ",
    "suggested_action": "hành động đề xuất",
    "urgency_level": <số từ 1-10>
}"""

    def process(self) -> Dict[str, Any]:
        """
        Chạy kiểm tra tất cả các khoản thanh toán

        Returns:
            Dict với kết quả xử lý
        """
        start_time = time.time()

        input_data = {"check_date": str(date.today()), "action": "daily_check"}

        log = self._log_start(None, input_data)

        try:
            results = {
                "reminders_sent": 0,
                "overdue_found": 0,
                "upcoming_found": 0,
                "details": [],
            }

            # Check upcoming payments (3-7 days)
            upcoming = self._check_upcoming_payments()
            results["upcoming_found"] = len(upcoming)

            for schedule in upcoming:
                self._send_reminder(schedule, "upcoming")
                results["reminders_sent"] += 1
                results["details"].append(
                    {
                        "type": "upcoming",
                        "contract_id": schedule.contract.id,
                        "borrower": schedule.contract.loan_request.borrower.username,
                        "due_date": str(schedule.due_date),
                        "amount": float(schedule.amount_due),
                    }
                )

            # Check due today
            due_today = self._check_due_today()
            for schedule in due_today:
                self._send_reminder(schedule, "due_today")
                results["reminders_sent"] += 1
                results["details"].append(
                    {
                        "type": "due_today",
                        "contract_id": schedule.contract.id,
                        "borrower": schedule.contract.loan_request.borrower.username,
                        "due_date": str(schedule.due_date),
                        "amount": float(schedule.amount_due),
                    }
                )

            # Check overdue payments
            overdue = self._check_overdue_payments()
            results["overdue_found"] = len(overdue)

            for schedule in overdue:
                self._send_reminder(schedule, "overdue")
                results["reminders_sent"] += 1
                results["details"].append(
                    {
                        "type": "overdue",
                        "contract_id": schedule.contract.id,
                        "borrower": schedule.contract.loan_request.borrower.username,
                        "due_date": str(schedule.due_date),
                        "amount": float(schedule.amount_due),
                        "days_overdue": (date.today() - schedule.due_date).days,
                    }
                )

            self._log_success(log, results, start_time)
            return {"success": True, "data": results}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def check_single_contract(self, contract) -> Dict[str, Any]:
        """Kiểm tra thanh toán cho một hợp đồng cụ thể"""
        from lending.models import RepaymentSchedule

        pending_schedules = RepaymentSchedule.objects.filter(
            contract=contract, is_paid=False
        ).order_by("due_date")

        result = {
            "contract_id": contract.id,
            "total_pending": pending_schedules.count(),
            "schedules": [],
        }

        for schedule in pending_schedules:
            days_until_due = (schedule.due_date - date.today()).days
            status = (
                "upcoming"
                if days_until_due > 0
                else ("due_today" if days_until_due == 0 else "overdue")
            )

            result["schedules"].append(
                {
                    "schedule_id": schedule.id,
                    "due_date": str(schedule.due_date),
                    "amount_due": float(schedule.amount_due),
                    "status": status,
                    "days_until_due": days_until_due,
                }
            )

        return result

    def _check_upcoming_payments(self) -> List:
        """Tìm các khoản sắp đến hạn (3-7 ngày)"""
        from lending.models import RepaymentSchedule

        today = date.today()
        upcoming_start = today + timedelta(days=3)
        upcoming_end = today + timedelta(days=7)

        return RepaymentSchedule.objects.filter(
            is_paid=False,
            reminder_sent=False,
            due_date__gte=upcoming_start,
            due_date__lte=upcoming_end,
            contract__is_active=True,
        ).select_related("contract__loan_request__borrower")

    def _check_due_today(self) -> List:
        """Tìm các khoản đến hạn hôm nay"""
        from lending.models import RepaymentSchedule

        return RepaymentSchedule.objects.filter(
            is_paid=False, due_date=date.today(), contract__is_active=True
        ).select_related("contract__loan_request__borrower")

    def _check_overdue_payments(self) -> List:
        """Tìm các khoản quá hạn"""
        from lending.models import RepaymentSchedule

        return RepaymentSchedule.objects.filter(
            is_paid=False, due_date__lt=date.today(), contract__is_active=True
        ).select_related("contract__loan_request__borrower", "contract__lender")

    def _send_reminder(self, schedule, reminder_type: str):
        """Gửi nhắc nhở thanh toán"""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        borrower = schedule.contract.loan_request.borrower
        days_diff = (schedule.due_date - date.today()).days

        reminder_input = {
            "borrower_name": borrower.username,
            "amount_due": float(schedule.amount_due),
            "due_date": str(schedule.due_date),
            "days_until_due": days_diff,
            "reminder_type": reminder_type,
            "contract_id": schedule.contract.id,
        }

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.SYSTEM_PROMPT),
                ("human", "Tạo tin nhắn nhắc nhở cho:\n{reminder_input}"),
            ]
        )

        chain = prompt | self._get_llm() | JsonOutputParser()

        try:
            result = chain.invoke({"reminder_input": str(reminder_input)})

            # Create notification
            self._create_notification(
                borrower,
                "PAYMENT_REMINDER",
                result.get("title", "Nhắc nhở thanh toán"),
                result.get(
                    "message",
                    f"Khoản thanh toán {schedule.amount_due:,.0f} VNĐ đến hạn {schedule.due_date}",
                ),
            )

            # Also notify lender if overdue
            if reminder_type == "overdue":
                lender = schedule.contract.lender
                self._create_notification(
                    lender,
                    "PAYMENT_REMINDER",
                    "Khoản vay quá hạn",
                    f"Khoản thanh toán từ {borrower.username} đã quá hạn {abs(days_diff)} ngày. "
                    f"Số tiền: {schedule.amount_due:,.0f} VNĐ.",
                )

            # Mark reminder as sent
            schedule.reminder_sent = True
            schedule.save()

        except Exception as e:
            # Fallback to simple notification
            self._create_notification(
                borrower,
                "PAYMENT_REMINDER",
                "Nhắc nhở thanh toán",
                f"Khoản thanh toán {schedule.amount_due:,.0f} VNĐ đến hạn ngày {schedule.due_date}.",
            )

    def mark_payment_completed(self, schedule_id: int) -> Dict[str, Any]:
        """Đánh dấu một khoản đã thanh toán"""
        from lending.models import RepaymentSchedule

        try:
            schedule = RepaymentSchedule.objects.get(id=schedule_id)
            schedule.is_paid = True
            schedule.paid_date = date.today()
            schedule.save()

            # Notify both parties
            borrower = schedule.contract.loan_request.borrower
            lender = schedule.contract.lender

            self._create_notification(
                borrower,
                "LOAN_FUNDED",
                "Thanh toán thành công!",
                f"Khoản thanh toán {schedule.amount_due:,.0f} VNĐ đã được ghi nhận.",
            )

            self._create_notification(
                lender,
                "LOAN_FUNDED",
                "Đã nhận thanh toán",
                f"Khoản thanh toán {schedule.amount_due:,.0f} VNĐ từ {borrower.username} đã được xác nhận.",
            )

            # Check if all payments completed
            remaining = RepaymentSchedule.objects.filter(
                contract=schedule.contract, is_paid=False
            ).count()

            if remaining == 0:
                schedule.contract.is_active = False
                schedule.contract.save()

            return {"success": True, "remaining_payments": remaining}

        except RepaymentSchedule.DoesNotExist:
            return {"success": False, "error": "Schedule not found"}
