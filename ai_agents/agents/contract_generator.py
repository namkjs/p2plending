"""
Agent Contract Generator: Tự động tạo hợp đồng vay
- Sinh nội dung hợp đồng
- Tạo lịch trả nợ
- Đảm bảo điều khoản hợp lệ
"""

import time
from typing import Any, Dict
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

from .base import BaseAgent


class ContractGeneratorAgent(BaseAgent):
    """Agent tự động tạo hợp đồng vay"""

    agent_type = "CONTRACT_GENERATOR"

    SYSTEM_PROMPT = """Bạn là chuyên gia pháp lý về hợp đồng cho vay P2P.
Nhiệm vụ: Tạo hợp đồng vay tiền rõ ràng, đầy đủ điều khoản pháp lý.

Hợp đồng cần bao gồm:
1. Thông tin các bên (Bên A: Người cho vay, Bên B: Người vay)
2. Số tiền vay, lãi suất, kỳ hạn
3. Phương thức thanh toán
4. Quyền và nghĩa vụ các bên
5. Điều khoản phạt vi phạm
6. Điều khoản tranh chấp
7. Điều khoản chấm dứt hợp đồng

Trả về JSON với format:
{
    "contract_title": "tiêu đề hợp đồng",
    "contract_number": "số hợp đồng",
    "contract_text": "nội dung đầy đủ hợp đồng bằng tiếng Việt",
    "key_terms": {
        "principal": <số tiền gốc>,
        "interest_rate": <lãi suất %/năm>,
        "duration_months": <số tháng>,
        "monthly_payment": <số tiền trả hàng tháng>,
        "total_payment": <tổng số tiền phải trả>,
        "late_fee_rate": <phí phạt trễ %>,
        "grace_period_days": <số ngày ân hạn>
    },
    "repayment_schedule": [
        {"period": 1, "due_date": "YYYY-MM-DD", "principal": <gốc>, "interest": <lãi>, "total": <tổng>},
        ...
    ]
}"""

    def process(self, loan_request, lender) -> Dict[str, Any]:
        """
        Tạo hợp đồng vay

        Args:
            loan_request: LoanRequest object
            lender: User object (người cho vay)

        Returns:
            Dict với hợp đồng và lịch trả nợ
        """
        start_time = time.time()

        input_data = {
            "loan_request_id": loan_request.id,
            "borrower": loan_request.borrower.username,
            "lender": lender.username,
            "amount": float(loan_request.amount),
            "interest_rate": loan_request.interest_rate,
            "duration_months": loan_request.duration_months,
            "purpose": loan_request.purpose,
        }

        log = self._log_start(loan_request.borrower, input_data)

        try:
            # Generate contract
            contract_data = self._generate_contract(loan_request, lender)

            # Create contract in database
            contract = self._create_contract(loan_request, lender, contract_data)

            # Create repayment schedule
            self._create_repayment_schedule(contract, contract_data)

            # Update loan request status
            loan_request.status = "FUNDED"
            loan_request.save()

            # Notify both parties
            self._notify_parties(loan_request, lender, contract)

            result = {
                "contract_id": contract.id,
                "contract_text": contract_data.get("contract_text", ""),
                "key_terms": contract_data.get("key_terms", {}),
            }

            self._log_success(log, result, start_time)
            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _generate_contract(self, loan_request, lender) -> Dict:
        """Sinh nội dung hợp đồng bằng AI"""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        # Get profiles
        borrower_profile = getattr(loan_request.borrower, "profile", None)
        lender_profile = getattr(lender, "profile", None)

        contract_input = {
            "borrower": {
                "name": (
                    borrower_profile.full_name
                    if borrower_profile
                    else loan_request.borrower.username
                ),
                "id_card": borrower_profile.id_card_number if borrower_profile else "",
                "address": borrower_profile.address if borrower_profile else "",
            },
            "lender": {
                "name": lender_profile.full_name if lender_profile else lender.username,
                "id_card": lender_profile.id_card_number if lender_profile else "",
                "address": lender_profile.address if lender_profile else "",
            },
            "loan_details": {
                "amount": float(loan_request.amount),
                "interest_rate": loan_request.interest_rate,
                "duration_months": loan_request.duration_months,
                "purpose": loan_request.purpose,
                "start_date": str(date.today()),
            },
        }

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.SYSTEM_PROMPT),
                ("human", "Tạo hợp đồng vay với thông tin sau:\n{contract_input}"),
            ]
        )

        chain = prompt | self._get_llm() | JsonOutputParser()
        result = chain.invoke({"contract_input": str(contract_input)})

        return result

    def _create_contract(self, loan_request, lender, contract_data: Dict):
        """Tạo hợp đồng trong database"""
        from lending.models import LoanContract

        contract = LoanContract.objects.create(
            loan_request=loan_request,
            lender=lender,
            contract_text=contract_data.get("contract_text", ""),
            is_active=True,
            is_disputed=False,
        )

        return contract

    def _create_repayment_schedule(self, contract, contract_data: Dict):
        """Tạo lịch trả nợ"""
        from lending.models import RepaymentSchedule

        schedule = contract_data.get("repayment_schedule", [])

        if schedule:
            for item in schedule:
                RepaymentSchedule.objects.create(
                    contract=contract,
                    due_date=item.get("due_date", date.today() + timedelta(days=30)),
                    amount_due=Decimal(str(item.get("total", 0))),
                    is_paid=False,
                )
        else:
            # Generate default schedule if AI didn't provide
            loan_request = contract.loan_request
            monthly_payment = self._calculate_monthly_payment(
                float(loan_request.amount),
                loan_request.interest_rate,
                loan_request.duration_months,
            )

            for i in range(loan_request.duration_months):
                due_date = date.today() + timedelta(days=30 * (i + 1))
                RepaymentSchedule.objects.create(
                    contract=contract,
                    due_date=due_date,
                    amount_due=Decimal(str(monthly_payment)),
                    is_paid=False,
                )

    def _calculate_monthly_payment(
        self, principal: float, annual_rate: float, months: int
    ) -> float:
        """Tính số tiền trả hàng tháng (công thức PMT)"""
        monthly_rate = annual_rate / 100 / 12
        if monthly_rate == 0:
            return principal / months

        payment = (
            principal
            * (monthly_rate * (1 + monthly_rate) ** months)
            / ((1 + monthly_rate) ** months - 1)
        )
        return round(payment, 2)

    def _notify_parties(self, loan_request, lender, contract):
        """Thông báo cho cả 2 bên"""
        # Notify borrower
        self._create_notification(
            loan_request.borrower,
            "CONTRACT_READY",
            "Hợp đồng vay đã được tạo!",
            f"Hợp đồng vay {loan_request.amount:,.0f} VNĐ đã được tạo. "
            f"Người cho vay: {lender.username}. Vui lòng xem chi tiết.",
        )

        # Notify lender
        self._create_notification(
            lender,
            "CONTRACT_READY",
            "Đầu tư thành công!",
            f"Hợp đồng cho vay {loan_request.amount:,.0f} VNĐ đã được tạo. "
            f"Người vay: {loan_request.borrower.username}.",
        )
