"""
Agent Contract Generator: Tạo hợp đồng vay với tools
- Sử dụng SQL tools để lấy thông tin
- Tạo hợp đồng PDF
- Quản lý signing process
"""

import time
import json
from typing import Any, Dict, List, Optional
from decimal import Decimal
from langchain_core.tools import tool

from .base import BaseAgent
from ai_agents.tools.sql_tools import (
    get_loan_detail,
    get_user_kyc_status,
    get_user_balance,
)


# ================= CONTRACT TOOLS =================


@tool("calculate_loan_schedule")
def calculate_loan_schedule(
    principal: float,
    interest_rate: float,
    duration_months: int,
    payment_method: str = "EQUAL_PRINCIPAL",
) -> str:
    """
    Tính lịch trả nợ chi tiết.

    Args:
        principal: Số tiền vay
        interest_rate: Lãi suất %/năm
        duration_months: Thời hạn vay (tháng)
        payment_method: Phương thức trả (EQUAL_PRINCIPAL hoặc EQUAL_PAYMENT)

    Returns:
        JSON lịch trả nợ
    """
    monthly_rate = interest_rate / 100 / 12
    schedule = []
    remaining = principal
    total_interest = 0
    total_payment = 0

    if payment_method == "EQUAL_PAYMENT":
        # Trả đều hàng tháng (gốc + lãi)
        if monthly_rate > 0:
            monthly_payment = (
                principal
                * (monthly_rate * (1 + monthly_rate) ** duration_months)
                / ((1 + monthly_rate) ** duration_months - 1)
            )
        else:
            monthly_payment = principal / duration_months

        for month in range(1, duration_months + 1):
            interest = remaining * monthly_rate
            principal_payment = monthly_payment - interest
            remaining -= principal_payment

            schedule.append(
                {
                    "month": month,
                    "principal_payment": round(principal_payment, 0),
                    "interest_payment": round(interest, 0),
                    "total_payment": round(monthly_payment, 0),
                    "remaining_balance": max(0, round(remaining, 0)),
                }
            )

            total_interest += interest
            total_payment += monthly_payment
    else:
        # Trả gốc đều, lãi giảm dần
        principal_payment = principal / duration_months

        for month in range(1, duration_months + 1):
            interest = remaining * monthly_rate
            payment = principal_payment + interest
            remaining -= principal_payment

            schedule.append(
                {
                    "month": month,
                    "principal_payment": round(principal_payment, 0),
                    "interest_payment": round(interest, 0),
                    "total_payment": round(payment, 0),
                    "remaining_balance": max(0, round(remaining, 0)),
                }
            )

            total_interest += interest
            total_payment += payment

    return json.dumps(
        {
            "success": True,
            "data": {
                "principal": principal,
                "interest_rate": interest_rate,
                "duration_months": duration_months,
                "payment_method": payment_method,
                "total_interest": round(total_interest, 0),
                "total_payment": round(total_payment, 0),
                "schedule": schedule,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


@tool("generate_contract_content")
def generate_contract_content(
    borrower_name: str,
    borrower_id: str,
    lender_name: str,
    lender_id: str,
    principal: float,
    interest_rate: float,
    duration_months: int,
    purpose: str,
) -> str:
    """
    Tạo nội dung hợp đồng vay.

    Args:
        borrower_name: Tên người vay
        borrower_id: CCCD người vay
        lender_name: Tên người cho vay
        lender_id: CCCD người cho vay
        principal: Số tiền vay
        interest_rate: Lãi suất %/năm
        duration_months: Thời hạn (tháng)
        purpose: Mục đích vay

    Returns:
        Nội dung hợp đồng
    """
    from datetime import datetime, timedelta

    start_date = datetime.now()
    end_date = start_date + timedelta(days=duration_months * 30)

    monthly_rate = interest_rate / 100 / 12
    total_interest = principal * monthly_rate * duration_months
    total_amount = principal + total_interest

    contract_number = f"HD-{start_date.strftime('%Y%m%d')}-{borrower_id[-4:]}"

    contract = f"""
═══════════════════════════════════════════════════════════════════
                        HỢP ĐỒNG VAY TIỀN
                    Số: {contract_number}
═══════════════════════════════════════════════════════════════════

Hôm nay, ngày {start_date.strftime('%d')} tháng {start_date.strftime('%m')} năm {start_date.strftime('%Y')}

Tại: Nền tảng P2P Lending

Chúng tôi gồm:

BÊN A (Bên cho vay):
- Họ và tên: {lender_name}
- CCCD/CMND: {lender_id}
- Vai trò: Người cho vay

BÊN B (Bên vay):
- Họ và tên: {borrower_name}
- CCCD/CMND: {borrower_id}
- Vai trò: Người vay

Hai bên thống nhất ký kết hợp đồng vay tiền với các điều khoản sau:

═══════════════════════════════════════════════════════════════════
                    ĐIỀU 1: SỐ TIỀN VAY
═══════════════════════════════════════════════════════════════════

Bên A đồng ý cho Bên B vay số tiền: {principal:,.0f} VNĐ
(Bằng chữ: {number_to_words(principal)})

═══════════════════════════════════════════════════════════════════
                    ĐIỀU 2: MỤC ĐÍCH VAY
═══════════════════════════════════════════════════════════════════

Mục đích vay: {purpose}

═══════════════════════════════════════════════════════════════════
                    ĐIỀU 3: THỜI HẠN VAY
═══════════════════════════════════════════════════════════════════

- Thời hạn vay: {duration_months} tháng
- Ngày bắt đầu: {start_date.strftime('%d/%m/%Y')}
- Ngày kết thúc: {end_date.strftime('%d/%m/%Y')}

═══════════════════════════════════════════════════════════════════
                    ĐIỀU 4: LÃI SUẤT
═══════════════════════════════════════════════════════════════════

- Lãi suất: {interest_rate}%/năm ({interest_rate/12:.2f}%/tháng)
- Tổng tiền lãi dự kiến: {total_interest:,.0f} VNĐ
- Tổng số tiền phải trả: {total_amount:,.0f} VNĐ

═══════════════════════════════════════════════════════════════════
                ĐIỀU 5: PHƯƠNG THỨC TRẢ NỢ
═══════════════════════════════════════════════════════════════════

- Phương thức: Trả góp hàng tháng
- Kỳ hạn thanh toán: Ngày {start_date.day} hàng tháng
- Số tiền mỗi kỳ: {total_amount/duration_months:,.0f} VNĐ (ước tính)

═══════════════════════════════════════════════════════════════════
                ĐIỀU 6: QUYỀN VÀ NGHĨA VỤ
═══════════════════════════════════════════════════════════════════

BÊN A có quyền:
1. Nhận lại đủ số tiền gốc và lãi theo đúng thỏa thuận
2. Yêu cầu Bên B trả nợ trước hạn nếu phát hiện gian lận
3. Khiếu nại qua nền tảng nếu có tranh chấp

BÊN B có nghĩa vụ:
1. Trả nợ gốc và lãi đúng hạn
2. Sử dụng tiền vay đúng mục đích
3. Thông báo khi có thay đổi thông tin liên lạc

═══════════════════════════════════════════════════════════════════
                ĐIỀU 7: PHẠT VI PHẠM
═══════════════════════════════════════════════════════════════════

- Trả chậm: Phạt 0.05%/ngày trên số tiền trả chậm
- Vi phạm nghiêm trọng: Yêu cầu trả toàn bộ nợ trước hạn

═══════════════════════════════════════════════════════════════════
                ĐIỀU 8: ĐIỀU KHOẢN CHUNG
═══════════════════════════════════════════════════════════════════

1. Hợp đồng có hiệu lực kể từ ngày ký
2. Mọi tranh chấp được giải quyết qua nền tảng P2P Lending
3. Hợp đồng được lập thành bản điện tử, có giá trị pháp lý

═══════════════════════════════════════════════════════════════════
                        CHỮ KÝ
═══════════════════════════════════════════════════════════════════

BÊN A (Người cho vay)          BÊN B (Người vay)

_____________________          _____________________
{lender_name[:20]:^20}         {borrower_name[:20]:^20}

Ngày ký: {start_date.strftime('%d/%m/%Y %H:%M')}

═══════════════════════════════════════════════════════════════════
"""

    return json.dumps(
        {
            "success": True,
            "data": {
                "contract_number": contract_number,
                "content": contract,
                "summary": {
                    "principal": principal,
                    "interest_rate": interest_rate,
                    "duration_months": duration_months,
                    "total_interest": total_interest,
                    "total_amount": total_amount,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            },
        },
        ensure_ascii=False,
    )


def number_to_words(n: float) -> str:
    """Convert number to Vietnamese words"""
    if n == 0:
        return "Không đồng"

    units = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ"]
    digits = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]

    n = int(n)
    if n >= 1000000000000:
        return f"{n:,} đồng"

    parts = []
    idx = 0

    while n > 0:
        group = n % 1000
        if group > 0:
            group_str = []
            hundreds = group // 100
            tens = (group % 100) // 10
            ones = group % 10

            if hundreds:
                group_str.append(f"{digits[hundreds]} trăm")
            if tens:
                if tens == 1:
                    group_str.append("mười")
                else:
                    group_str.append(f"{digits[tens]} mươi")
            if ones:
                if ones == 1 and tens > 1:
                    group_str.append("mốt")
                elif ones == 5 and tens:
                    group_str.append("lăm")
                else:
                    group_str.append(digits[ones])

            if units[idx]:
                group_str.append(units[idx])

            parts.append(" ".join(group_str))

        n //= 1000
        idx += 1

    parts.reverse()
    return " ".join(parts).strip() + " đồng"


@tool("validate_contract_parties")
def validate_contract_parties(borrower_id: int, lender_id: int) -> str:
    """
    Kiểm tra tính hợp lệ của các bên trong hợp đồng.

    Args:
        borrower_id: ID của người vay
        lender_id: ID của người cho vay

    Returns:
        Kết quả kiểm tra
    """
    from django.contrib.auth.models import User
    from user.models import UserProfile

    errors = []
    warnings = []

    # Check borrower
    try:
        borrower = User.objects.get(id=borrower_id)
        borrower_profile = UserProfile.objects.get(user=borrower)

        if borrower_profile.kyc_status != "VERIFIED":
            errors.append("Người vay chưa xác thực KYC")

        borrower_info = {
            "id": borrower_id,
            "name": borrower_profile.full_name or borrower.username,
            "id_card": borrower_profile.id_card_number or "N/A",
            "kyc_status": borrower_profile.kyc_status,
        }
    except:
        errors.append(f"Không tìm thấy người vay (ID: {borrower_id})")
        borrower_info = None

    # Check lender
    try:
        lender = User.objects.get(id=lender_id)
        lender_profile = UserProfile.objects.get(user=lender)

        if lender_profile.kyc_status != "VERIFIED":
            warnings.append("Người cho vay chưa xác thực KYC")

        lender_info = {
            "id": lender_id,
            "name": lender_profile.full_name or lender.username,
            "id_card": lender_profile.id_card_number or "N/A",
            "kyc_status": lender_profile.kyc_status,
        }
    except:
        errors.append(f"Không tìm thấy người cho vay (ID: {lender_id})")
        lender_info = None

    # Check if same person
    if borrower_id == lender_id:
        errors.append("Người vay và người cho vay không thể là cùng một người")

    return json.dumps(
        {
            "success": len(errors) == 0,
            "borrower": borrower_info,
            "lender": lender_info,
            "errors": errors,
            "warnings": warnings,
        },
        ensure_ascii=False,
    )


@tool("create_contract_record")
def create_contract_record(
    loan_request_id: int, lender_id: int, contract_content: str
) -> str:
    """
    Tạo bản ghi hợp đồng trong database.

    Args:
        loan_request_id: ID yêu cầu vay
        lender_id: ID người cho vay
        contract_content: Nội dung hợp đồng

    Returns:
        Kết quả tạo hợp đồng
    """
    from lending.models import LoanRequest, LoanContract
    from django.contrib.auth.models import User
    from datetime import datetime, timedelta
    import hashlib

    try:
        loan_request = LoanRequest.objects.get(id=loan_request_id)
        lender = User.objects.get(id=lender_id)

        # Generate contract number
        contract_number = (
            f"HD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{loan_request_id}"
        )

        # Calculate dates
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=loan_request.duration_months * 30)

        # Calculate amounts
        monthly_rate = float(loan_request.interest_rate) / 100 / 12
        total_interest = (
            float(loan_request.amount) * monthly_rate * loan_request.duration_months
        )

        # Create contract
        contract = LoanContract.objects.create(
            contract_number=contract_number,
            loan_request=loan_request,
            borrower=loan_request.borrower,
            lender=lender,
            principal_amount=loan_request.amount,
            interest_rate=loan_request.interest_rate,
            total_interest=total_interest,
            total_amount=float(loan_request.amount) + total_interest,
            start_date=start_date,
            end_date=end_date,
            contract_content=contract_content,
            status="PENDING_SIGNATURES",
        )

        # Update loan request status
        loan_request.status = "CONTRACT_CREATED"
        loan_request.save()

        return json.dumps(
            {
                "success": True,
                "data": {
                    "contract_id": contract.id,
                    "contract_number": contract_number,
                    "status": contract.status,
                    "principal": float(contract.principal_amount),
                    "total_amount": float(contract.total_amount),
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                },
            },
            ensure_ascii=False,
        )

    except LoanRequest.DoesNotExist:
        return json.dumps(
            {
                "success": False,
                "error": f"Không tìm thấy yêu cầu vay ID {loan_request_id}",
            }
        )
    except User.DoesNotExist:
        return json.dumps(
            {"success": False, "error": f"Không tìm thấy người cho vay ID {lender_id}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ================= AGENT CLASS =================


class ContractGeneratorAgent(BaseAgent):
    """Agent tạo hợp đồng vay với tools"""

    agent_type = "CONTRACT_GENERATOR"

    system_prompt = """Bạn là Contract Generator Agent cho nền tảng P2P Lending.

Nhiệm vụ của bạn:
1. Tạo hợp đồng vay chuyên nghiệp
2. Tính toán lịch trả nợ chi tiết
3. Xác thực thông tin các bên tham gia
4. Quản lý quy trình ký hợp đồng

Quy trình tạo hợp đồng:
1. Xác thực người vay và người cho vay
2. Kiểm tra KYC status
3. Tính lịch trả nợ
4. Tạo nội dung hợp đồng
5. Lưu vào database

Bạn có thể sử dụng các công cụ sau:
- validate_contract_parties: Kiểm tra tính hợp lệ
- calculate_loan_schedule: Tính lịch trả nợ
- generate_contract_content: Tạo nội dung hợp đồng
- create_contract_record: Lưu hợp đồng vào DB
- get_loan_detail: Lấy thông tin khoản vay
- get_user_kyc_status: Kiểm tra KYC

Hãy tạo hợp đồng chính xác và đầy đủ thông tin."""

    tools = [
        validate_contract_parties,
        calculate_loan_schedule,
        generate_contract_content,
        create_contract_record,
        get_loan_detail,
        get_user_kyc_status,
        get_user_balance,
    ]

    def process(
        self, loan_request, lender, payment_method: str = "EQUAL_PRINCIPAL"
    ) -> Dict[str, Any]:
        """
        Tạo hợp đồng vay

        Args:
            loan_request: LoanRequest object
            lender: User object (người cho vay)
            payment_method: Phương thức trả nợ

        Returns:
            Dict với thông tin hợp đồng
        """
        start_time = time.time()

        input_data = {
            "loan_request_id": loan_request.id,
            "borrower_id": loan_request.borrower.id,
            "lender_id": lender.id,
            "amount": str(loan_request.amount),
            "interest_rate": str(loan_request.interest_rate),
            "duration_months": loan_request.duration_months,
        }

        log = self._log_start(loan_request.borrower, input_data)

        try:
            # 1. Validate parties
            validation = validate_contract_parties.invoke(
                loan_request.borrower.id, lender.id
            )
            validation_data = json.loads(validation)

            if not validation_data.get("success"):
                errors = validation_data.get("errors", [])
                raise ValueError(f"Validation failed: {', '.join(errors)}")

            borrower_info = validation_data.get("borrower", {})
            lender_info = validation_data.get("lender", {})

            # 2. Calculate schedule
            schedule_result = calculate_loan_schedule.invoke(
                float(loan_request.amount),
                float(loan_request.interest_rate),
                loan_request.duration_months,
                payment_method,
            )
            schedule_data = json.loads(schedule_result)

            # 3. Generate contract content
            contract_result = generate_contract_content.invoke(
                borrower_info.get("name", "N/A"),
                borrower_info.get("id_card", "N/A"),
                lender_info.get("name", "N/A"),
                lender_info.get("id_card", "N/A"),
                float(loan_request.amount),
                float(loan_request.interest_rate),
                loan_request.duration_months,
                loan_request.purpose,
            )
            contract_data = json.loads(contract_result)

            if not contract_data.get("success"):
                raise ValueError("Failed to generate contract content")

            contract_content = contract_data["data"]["content"]

            # 4. Create contract record
            create_result = create_contract_record.invoke(
                loan_request.id, lender.id, contract_content
            )
            create_data = json.loads(create_result)

            if not create_data.get("success"):
                raise ValueError(create_data.get("error", "Failed to create contract"))

            result = {
                "contract": create_data["data"],
                "schedule": schedule_data.get("data", {}),
                "parties": {
                    "borrower": borrower_info,
                    "lender": lender_info,
                },
            }

            self._log_success(log, result, start_time)

            # Notify both parties
            self._notify_contract_created(loan_request, lender, create_data["data"])

            return {"success": True, "data": result}

        except Exception as e:
            self._log_failure(log, str(e), start_time)
            return {"success": False, "error": str(e)}

    def _notify_contract_created(self, loan_request, lender, contract_data):
        """Thông báo hợp đồng đã tạo"""
        # Notify borrower
        self._create_notification(
            user=loan_request.borrower,
            notification_type="CONTRACT_STATUS",
            title="📄 Hợp đồng vay đã được tạo",
            message=f"""Hợp đồng #{contract_data['contract_number']} đã được tạo.
Số tiền vay: {contract_data['principal']:,.0f} VNĐ
Tổng số tiền trả: {contract_data['total_amount']:,.0f} VNĐ
Thời hạn: {loan_request.duration_months} tháng
Vui lòng xem và ký hợp đồng để hoàn tất.""",
            related_loan_id=loan_request.id,
        )

        # Notify lender
        self._create_notification(
            user=lender,
            notification_type="CONTRACT_STATUS",
            title="📄 Hợp đồng cho vay đã được tạo",
            message=f"""Hợp đồng #{contract_data['contract_number']} với {loan_request.borrower.username} đã được tạo.
Số tiền cho vay: {contract_data['principal']:,.0f} VNĐ
Lãi dự kiến: {contract_data['total_amount'] - contract_data['principal']:,.0f} VNĐ
Vui lòng xem và ký hợp đồng.""",
            related_loan_id=loan_request.id,
        )

    def sign_contract(
        self, contract_id: int, user, signature_type: str = "borrower"
    ) -> Dict:
        """
        Ký hợp đồng

        Args:
            contract_id: ID hợp đồng
            user: User ký
            signature_type: 'borrower' hoặc 'lender'
        """
        from lending.models import LoanContract
        from datetime import datetime

        try:
            contract = LoanContract.objects.get(id=contract_id)

            if signature_type == "borrower":
                if contract.borrower != user:
                    return {
                        "success": False,
                        "error": "Bạn không phải người vay trong hợp đồng này",
                    }
                contract.borrower_signed = True
                contract.borrower_signed_at = datetime.now()
            else:
                if contract.lender != user:
                    return {
                        "success": False,
                        "error": "Bạn không phải người cho vay trong hợp đồng này",
                    }
                contract.lender_signed = True
                contract.lender_signed_at = datetime.now()

            # Check if both signed
            if contract.borrower_signed and contract.lender_signed:
                contract.status = "ACTIVE"
                contract.is_active = True

                # Update loan request
                contract.loan_request.status = "FUNDED"
                contract.loan_request.save()

                # Create payment schedule
                self._create_payment_schedule(contract)

            contract.save()

            return {
                "success": True,
                "status": contract.status,
                "borrower_signed": contract.borrower_signed,
                "lender_signed": contract.lender_signed,
            }

        except LoanContract.DoesNotExist:
            return {"success": False, "error": "Không tìm thấy hợp đồng"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_payment_schedule(self, contract):
        """Tạo lịch thanh toán sau khi hợp đồng có hiệu lực"""
        from lending.models import PaymentSchedule
        from datetime import timedelta

        # Calculate schedule
        schedule_result = calculate_loan_schedule.invoke(
            float(contract.principal_amount),
            float(contract.interest_rate),
            (contract.end_date - contract.start_date).days // 30,
            "EQUAL_PRINCIPAL",
        )
        schedule_data = json.loads(schedule_result)

        if schedule_data.get("success"):
            for item in schedule_data["data"]["schedule"]:
                due_date = contract.start_date + timedelta(days=item["month"] * 30)

                PaymentSchedule.objects.create(
                    contract=contract,
                    installment_number=item["month"],
                    due_date=due_date,
                    principal_amount=item["principal_payment"],
                    interest_amount=item["interest_payment"],
                    total_amount=item["total_payment"],
                )
