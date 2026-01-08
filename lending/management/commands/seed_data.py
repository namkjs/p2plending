import random
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, date

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from user.models import UserProfile
from lending.models import (
    LoanRequest,
    LenderProfile,
    BorrowerRiskProfile,
    LenderMatchResult,
    LoanContract,
    PaymentSchedule,
    PaymentTransaction,
    RepaymentSchedule,
    Dispute,
    DisputeEvidence,
)


def d2(x) -> Decimal:
    """Decimal with 2 dp."""
    if isinstance(x, Decimal):
        v = x
    else:
        v = Decimal(str(x))
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = "Generate large mock data for P2P Lending App (≈100k loans) using bulk inserts."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Delete all seeded data before generating new data")
        parser.add_argument("--loans", type=int, default=100_000, help="Number of LoanRequest to generate (default: 100000)")
        parser.add_argument("--borrowers", type=int, default=20_000, help="Number of borrowers to generate (default: 20000)")
        parser.add_argument("--lenders", type=int, default=2_000, help="Number of lenders to generate (default: 2000)")
        parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
        parser.add_argument("--batch", type=int, default=5000, help="Bulk batch size (default: 5000)")
        parser.add_argument("--matches-per-loan", type=int, default=3, help="How many lenders to match per PENDING/APPROVED loan (default: 3)")
        parser.add_argument("--funded-ratio", type=float, default=0.25, help="Ratio of FUNDED loans (default: 0.25)")
        parser.add_argument("--approved-ratio", type=float, default=0.25, help="Ratio of APPROVED loans (default: 0.25)")
        parser.add_argument("--pending-ratio", type=float, default=0.25, help="Ratio of PENDING loans (default: 0.25)")
        # REJECTED ratio = 1 - sum(3 above)
        parser.add_argument("--create-disputes", action="store_true", help="Create disputes for some late schedules")

    def _progress(self, msg: str):
        self.stdout.write(msg)

    def handle(self, *args, **kwargs):
        random.seed(kwargs["seed"])

        loans_target = kwargs["loans"]
        borrowers_n = kwargs["borrowers"]
        lenders_n = kwargs["lenders"]
        batch_size = kwargs["batch"]
        matches_per_loan = kwargs["matches_per_loan"]

        funded_ratio = float(kwargs["funded_ratio"])
        approved_ratio = float(kwargs["approved_ratio"])
        pending_ratio = float(kwargs["pending_ratio"])

        if funded_ratio + approved_ratio + pending_ratio > 1.0:
            raise ValueError("Sum of funded_ratio + approved_ratio + pending_ratio must be <= 1.0")

        create_disputes = kwargs["create_disputes"]

        from django.contrib.auth import get_user_model
        User = get_user_model()

        today = timezone.now().date()

        # -------------------------
        # DELETE OLD DATA (if asked)
        # -------------------------
        if kwargs["delete"]:
            self._progress("Deleting ALL data and resetting auto-increment IDs...")
            
            from django.db import connection
            
            # Table names in order (respect FK constraints - children first)
            tables_to_truncate = [
                "lending_disputeevidence",
                "lending_paymenttransaction",
                "lending_paymentschedule",
                "lending_repaymentschedule",
                "lending_dispute",
                "lending_loancontract",
                "lending_lendermatchresult",
                "lending_loanrequest",
                "lending_lenderprofile",
                "lending_borrowerriskprofile",
                "user_userprofile",
            ]
            
            with connection.cursor() as cursor:
                # Check if MySQL or PostgreSQL
                db_vendor = connection.vendor
                
                if db_vendor == "mysql":
                    # Disable FK checks temporarily for MySQL
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                    for table in tables_to_truncate:
                        try:
                            cursor.execute(f"TRUNCATE TABLE `{table}`;")
                        except Exception as e:
                            self._progress(f"Warning: Could not truncate {table}: {e}")
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
                    
                    # Truncate auth_user (only seed users)
                    cursor.execute("DELETE FROM auth_user WHERE username LIKE 'seed_borrower_%' OR username LIKE 'seed_lender_%';")
                    # Reset auth_user auto_increment to max(id) + 1 or 1 if empty
                    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM auth_user;")
                    max_id = cursor.fetchone()[0]
                    cursor.execute(f"ALTER TABLE auth_user AUTO_INCREMENT = {max_id + 1};")
                    
                elif db_vendor == "postgresql":
                    for table in tables_to_truncate:
                        try:
                            cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
                        except Exception as e:
                            self._progress(f"Warning: Could not truncate {table}: {e}")
                    
                    # Delete seed users
                    cursor.execute("DELETE FROM auth_user WHERE username LIKE 'seed_borrower_%' OR username LIKE 'seed_lender_%';")
                    
                elif db_vendor == "sqlite":
                    # SQLite: use DELETE and reset sequence
                    for table in tables_to_truncate:
                        try:
                            cursor.execute(f'DELETE FROM "{table}";')
                            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}';")
                        except Exception as e:
                            self._progress(f"Warning: Could not delete from {table}: {e}")
                    
                    # Delete seed users
                    cursor.execute("DELETE FROM auth_user WHERE username LIKE 'seed_borrower_%' OR username LIKE 'seed_lender_%';")
                    try:
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name='auth_user';")
                    except Exception:
                        pass
                else:
                    # Fallback: use Django ORM delete (won't reset auto-increment)
                    self._progress(f"Warning: Unknown DB vendor '{db_vendor}', using ORM delete (IDs won't reset)")
                    DisputeEvidence.objects.all().delete()
                    PaymentTransaction.objects.all().delete()
                    PaymentSchedule.objects.all().delete()
                    RepaymentSchedule.objects.all().delete()
                    Dispute.objects.all().delete()
                    LoanContract.objects.all().delete()
                    LenderMatchResult.objects.all().delete()
                    LoanRequest.objects.all().delete()
                    LenderProfile.objects.all().delete()
                    BorrowerRiskProfile.objects.all().delete()
                    UserProfile.objects.all().delete()
                    User.objects.filter(username__startswith="seed_borrower_").delete()
                    User.objects.filter(username__startswith="seed_lender_").delete()
            
            self._progress("All data deleted and IDs reset.")

        self._progress("Starting large data seeding...")

        password_hash = make_password("password123")

        # -------------------------
        # 1) CREATE USERS (Borrowers + Lenders)
        # -------------------------
        self._progress(f"Creating {borrowers_n} borrowers + {lenders_n} lenders...")

        borrower_users = [
            User(
                username=f"seed_borrower_{i}",
                password=password_hash,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            for i in range(1, borrowers_n + 1)
        ]
        lender_users = [
            User(
                username=f"seed_lender_{i}",
                password=password_hash,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            for i in range(1, lenders_n + 1)
        ]

        User.objects.bulk_create(borrower_users, batch_size=batch_size, ignore_conflicts=True)
        User.objects.bulk_create(lender_users, batch_size=batch_size, ignore_conflicts=True)

        borrower_ids = list(
            User.objects.filter(username__startswith="seed_borrower_").values_list("id", flat=True)
        )
        lender_ids = list(
            User.objects.filter(username__startswith="seed_lender_").values_list("id", flat=True)
        )

        if not borrower_ids or not lender_ids:
            raise RuntimeError("Failed to create/fetch seeded users. Check username uniqueness / permissions.")

        self._progress(f"Borrowers in DB: {len(borrower_ids)} | Lenders in DB: {len(lender_ids)}")

        # -------------------------
        # 2) CREATE UserProfile, BorrowerRiskProfile, LenderProfile
        # -------------------------
        self._progress("Creating UserProfile + RiskProfile + LenderProfile...")

        borrower_profiles = []
        lender_profiles = []
        borrower_risks = []
        lender_profiles_tbl = []

        # Borrower profiles + risks (sử dụng user_id thay vì user object)
        for uid in borrower_ids:
            borrower_profiles.append(
                UserProfile(
                    user_id=uid,
                    balance=d2(0),
                    full_name=f"Borrower {uid}",
                    id_card_number=f"ID{uid:09d}",
                    address="Hanoi, Vietnam",
                    kyc_status="VERIFIED",
                    kyc_note="",
                    company_name="",
                    date_of_birth=date(1995, 1, 1),
                    gender="MALE",
                    hometown="Hanoi",
                    monthly_income=d2(random.randint(10, 80) * 1_000_000),
                    occupation="Employee",
                    ocr_data=None,
                    ocr_match_score=None,
                    ocr_verified=True,
                    phone_number=f"09{uid:08d}"[:15],
                )
            )
            borrower_risks.append(
                BorrowerRiskProfile(
                    user_id=uid,
                    credit_score=random.randint(450, 900),
                    risk_level=random.choice(["LOW", "MEDIUM", "HIGH"]),
                    income_stability=random.uniform(40, 95),
                    debt_to_income_ratio=random.uniform(0.1, 0.8),
                    payment_history_score=random.uniform(30, 95),
                    ai_analysis=None,
                )
            )

        # Lender profiles
        for uid in lender_ids:
            lender_profiles.append(
                UserProfile(
                    user_id=uid,
                    balance=d2(500_000_000),
                    full_name=f"Lender {uid}",
                    id_card_number=f"ID{uid:09d}",
                    address="HCMC, Vietnam",
                    kyc_status="VERIFIED",
                    kyc_note="",
                    company_name="",
                    date_of_birth=date(1990, 1, 1),
                    gender="FEMALE",
                    hometown="HCMC",
                    monthly_income=None,
                    occupation="Investor",
                    ocr_data=None,
                    ocr_match_score=None,
                    ocr_verified=True,
                    phone_number=f"08{uid:08d}"[:15],
                )
            )
            lender_profiles_tbl.append(
                LenderProfile(
                    user_id=uid,
                    min_amount=d2(1_000_000),
                    max_amount=d2(200_000_000),
                    min_interest_rate=random.choice([7.5, 8.0, 9.0, 10.0]),
                    preferred_duration_min=1,
                    preferred_duration_max=random.choice([12, 24, 36]),
                    risk_tolerance=random.choice(["LOW", "MEDIUM", "HIGH"]),
                    total_invested=d2(0),
                    total_returns=d2(0),
                    active_investments=0,
                    is_active=True,
                )
            )

        # Insert profiles in chunks
        for i in range(0, len(borrower_profiles), batch_size):
            UserProfile.objects.bulk_create(borrower_profiles[i:i + batch_size], batch_size=batch_size, ignore_conflicts=True)
        for i in range(0, len(lender_profiles), batch_size):
            UserProfile.objects.bulk_create(lender_profiles[i:i + batch_size], batch_size=batch_size, ignore_conflicts=True)
        for i in range(0, len(borrower_risks), batch_size):
            BorrowerRiskProfile.objects.bulk_create(borrower_risks[i:i + batch_size], batch_size=batch_size, ignore_conflicts=True)
        for i in range(0, len(lender_profiles_tbl), batch_size):
            LenderProfile.objects.bulk_create(lender_profiles_tbl[i:i + batch_size], batch_size=batch_size, ignore_conflicts=True)

        self._progress("Profiles created.")

        # -------------------------
        # 3) CREATE LoanRequest (≈100k) in batches
        # -------------------------
        self._progress(f"Creating {loans_target} LoanRequest...")

        # Build status distribution
        statuses = (
            ["FUNDED"] * int(funded_ratio * 1000)
            + ["APPROVED"] * int(approved_ratio * 1000)
            + ["PENDING"] * int(pending_ratio * 1000)
            + ["REJECTED"] * max(0, 1000 - (int(funded_ratio * 1000) + int(approved_ratio * 1000) + int(pending_ratio * 1000)))
        )
        if not statuses:
            statuses = ["PENDING", "APPROVED", "FUNDED", "REJECTED"]

        durations = [6, 12, 18, 24, 36]
        purpose_samples = [
            "Vay tiêu dùng",
            "Vay kinh doanh nhỏ",
            "Vay mua xe",
            "Vay học phí",
            "Vay sửa nhà",
        ]

        total_created = 0
        contracts_created = 0
        schedules_created = 0
        repayment_schedules_created = 0
        txns_created = 0
        disputes_created = 0
        evidences_created = 0
        matches_created = 0

        # Dispute types and statuses for variety
        dispute_types = ["LATE_PAYMENT", "WRONG_AMOUNT", "CONTRACT_VIOLATION", "OTHER"]
        dispute_statuses = ["OPEN", "IN_REVIEW", "RESOLVED", "ESCALATED"]
        dispute_descriptions = {
            "LATE_PAYMENT": "Người vay chậm thanh toán kỳ {inst_num}. Yêu cầu phạt trễ hạn và đốc thu nợ.",
            "WRONG_AMOUNT": "Số tiền thanh toán kỳ {inst_num} không khớp với số tiền quy định trong hợp đồng.",
            "CONTRACT_VIOLATION": "Vi phạm điều khoản hợp đồng: Người vay sử dụng vốn sai mục đích.",
            "OTHER": "Tranh chấp khác liên quan đến hợp đồng vay. Cần xem xét và giải quyết.",
        }

        # Evidence descriptions
        evidence_descriptions = {
            "TEXT": "Bản ghi lịch sử thanh toán từ hệ thống cho thấy các khoản trễ hạn.",
            "IMAGE": "Ảnh chụp màn hình giao dịch ngân hàng làm bằng chứng.",
            "PDF": "Hợp đồng vay có chữ ký của hai bên.",
            "OTHER": "Tài liệu bổ sung liên quan đến tranh chấp.",
        }

        # Process in batches
        for start in range(0, loans_target, batch_size):
            end = min(start + batch_size, loans_target)

            with transaction.atomic():
                # ========== STEP A: Prepare loan data as dicts (NO object references) ==========
                loan_data_list = []
                for i in range(start, end):
                    borrower_id = borrower_ids[i % len(borrower_ids)]
                    status = random.choice(statuses)
                    amount = d2(random.randint(5, 200) * 1_000_000)
                    duration = random.choice(durations)
                    interest_rate = random.choice([10.5, 11.5, 12.5, 13.5, 15.0])

                    loan_data_list.append({
                        "borrower_id": borrower_id,
                        "amount": amount,
                        "interest_rate": interest_rate,
                        "duration_months": duration,
                        "purpose": random.choice(purpose_samples),
                        "status": status,
                    })

                # ========== STEP B: Create LoanRequest using _id fields only ==========
                loan_objs = [
                    LoanRequest(
                        borrower_id=data["borrower_id"],
                        amount=data["amount"],
                        interest_rate=data["interest_rate"],
                        duration_months=data["duration_months"],
                        purpose=data["purpose"],
                        status=data["status"],
                    )
                    for data in loan_data_list
                ]

                LoanRequest.objects.bulk_create(loan_objs, batch_size=batch_size)
                total_created += len(loan_objs)

                # Re-fetch IDs của các loan vừa tạo
                new_loan_ids = list(
                    LoanRequest.objects.order_by("-id").values_list("id", flat=True)[:len(loan_objs)]
                )
                new_loan_ids.reverse()

                # ========== STEP C: Create LenderMatchResult for PENDING/APPROVED ==========
                match_objs = []
                for data, loan_id in zip(loan_data_list, new_loan_ids):
                    if data["status"] in ("PENDING", "APPROVED"):
                        k = min(matches_per_loan, len(lender_ids))
                        for lid in random.sample(lender_ids, k=k):
                            match_objs.append(
                                LenderMatchResult(
                                    loan_request_id=loan_id,
                                    lender_id=lid,
                                    match_score=random.uniform(60, 99),
                                    match_reasons=["amount_fit", "interest_fit"],
                                    is_notified=True,
                                    is_viewed=False,
                                    is_interested=(random.random() < 0.1),
                                )
                            )

                if match_objs:
                    LenderMatchResult.objects.bulk_create(match_objs, batch_size=batch_size, ignore_conflicts=True)
                    matches_created += len(match_objs)

                # ========== STEP D: Create LoanContract for FUNDED loans ==========
                funded_pairs = [
                    (data, loan_id)
                    for data, loan_id in zip(loan_data_list, new_loan_ids)
                    if data["status"] == "FUNDED"
                ]

                if not funded_pairs:
                    continue

                # Store loan info by ID for schedule creation
                loan_info_by_id = {}
                contract_objs = []

                for data, loan_id in funded_pairs:
                    lender_id = random.choice(lender_ids)

                    principal = data["amount"]
                    duration_months = data["duration_months"]
                    interest_rate_val = data["interest_rate"]

                    years = Decimal(str(duration_months)) / Decimal("12")
                    rate = Decimal(str(interest_rate_val)) / Decimal("100")
                    total_interest = d2(principal * rate * years)
                    total_amount = d2(principal + total_interest)

                    start_date = today - timedelta(days=random.randint(0, 180))
                    end_date = start_date + timedelta(days=30 * duration_months)

                    # Store info for schedule creation later
                    loan_info_by_id[loan_id] = {
                        "amount": principal,
                        "duration_months": duration_months,
                        "interest_rate": interest_rate_val,
                        "borrower_id": data["borrower_id"],
                        "lender_id": lender_id,
                        "start_date": start_date,
                    }

                    contract_objs.append(
                        LoanContract(
                            loan_request_id=loan_id,
                            lender_id=lender_id,
                            borrower_id=data["borrower_id"],
                            contract_content="Hợp đồng vay vốn (mock)...",
                            contract_text="Hợp đồng vay vốn (legacy mock)...",
                            contract_number=None,
                            principal_amount=principal,
                            interest_rate=interest_rate_val,
                            total_interest=total_interest,
                            total_amount=total_amount,
                            start_date=start_date,
                            end_date=end_date,
                            status="ACTIVE",
                            is_active=True,
                            is_disputed=False,
                            borrower_signed=True,
                            borrower_signed_at=timezone.now() - timedelta(days=random.randint(0, 30)),
                            lender_signed=True,
                            lender_signed_at=timezone.now() - timedelta(days=random.randint(0, 30)),
                        )
                    )

                LoanContract.objects.bulk_create(contract_objs, batch_size=batch_size, ignore_conflicts=True)
                contracts_created += len(contract_objs)

                # ========== STEP E: Re-fetch contracts to get their IDs ==========
                funded_loan_ids = [loan_id for _, loan_id in funded_pairs]
                contract_rows = list(
                    LoanContract.objects.filter(loan_request_id__in=funded_loan_ids)
                    .values("id", "loan_request_id", "lender_id", "borrower_id", "start_date")
                )
                contract_by_loan_id = {r["loan_request_id"]: r for r in contract_rows}

                # ========== STEP F: Create PaymentSchedule + RepaymentSchedule for each contract ==========
                schedule_objs = []
                repayment_schedule_objs = []
                late_contract_ids = set()
                paid_schedule_keys = []  # (contract_id, installment_number) for PAID schedules
                late_schedule_info = []  # Collect info for potential disputes

                for loan_id, info in loan_info_by_id.items():
                    contract_row = contract_by_loan_id.get(loan_id)
                    if not contract_row:
                        continue

                    contract_id = contract_row["id"]
                    c_start = contract_row["start_date"]
                    months = info["duration_months"]
                    amount = info["amount"]
                    interest_rate_val = info["interest_rate"]

                    principal_each = amount / Decimal(months)
                    years = Decimal(months) / Decimal("12")
                    rate = Decimal(str(interest_rate_val)) / Decimal("100")
                    total_interest = amount * rate * years
                    interest_each = total_interest / Decimal(months)

                    for inst in range(1, months + 1):
                        due = c_start + timedelta(days=30 * inst)
                        total_amt = principal_each + interest_each

                        status = "PENDING"
                        paid_amount = None
                        paid_date = None
                        late_fee = d2(0)
                        late_days = 0
                        is_paid = False
                        repayment_paid_date = None

                        if due < today:
                            r = random.random()
                            if r < 0.65:
                                status = "PAID"
                                paid_amount = d2(total_amt)
                                paid_date = due + timedelta(days=random.randint(0, 5))
                                paid_schedule_keys.append((contract_id, inst))
                                is_paid = True
                                repayment_paid_date = paid_date
                            else:
                                status = "LATE"
                                late_days = random.randint(1, 30)
                                late_fee = d2(min(200_000, late_days * 10_000))
                                late_contract_ids.add(contract_id)
                                # Store late schedule info for dispute creation
                                late_schedule_info.append({
                                    "contract_id": contract_id,
                                    "installment_number": inst,
                                    "late_days": late_days,
                                    "borrower_id": contract_row["borrower_id"],
                                    "lender_id": contract_row["lender_id"],
                                })

                        # PaymentSchedule (detailed)
                        schedule_objs.append(
                            PaymentSchedule(
                                contract_id=contract_id,
                                installment_number=inst,
                                due_date=due,
                                principal_amount=d2(principal_each),
                                interest_amount=d2(interest_each),
                                total_amount=d2(total_amt),
                                paid_amount=paid_amount,
                                paid_date=paid_date,
                                late_fee=late_fee,
                                late_days=late_days,
                                status=status,
                                note="",
                            )
                        )

                        # RepaymentSchedule (legacy - simpler structure)
                        repayment_schedule_objs.append(
                            RepaymentSchedule(
                                contract_id=contract_id,
                                due_date=due,
                                amount_due=d2(total_amt),
                                is_paid=is_paid,
                                paid_date=repayment_paid_date,
                                reminder_sent=(due <= today),  # reminder sent if due date has passed
                            )
                        )

                if schedule_objs:
                    PaymentSchedule.objects.bulk_create(schedule_objs, batch_size=batch_size, ignore_conflicts=True)
                    schedules_created += len(schedule_objs)

                if repayment_schedule_objs:
                    RepaymentSchedule.objects.bulk_create(repayment_schedule_objs, batch_size=batch_size, ignore_conflicts=True)
                    repayment_schedules_created += len(repayment_schedule_objs)

                # ========== STEP G: Create PaymentTransaction for PAID schedules ==========
                if paid_schedule_keys:
                    # Re-fetch PAID schedules to get their IDs
                    contract_ids_in_batch = list(contract_by_loan_id.values())
                    contract_id_list = [c["id"] for c in contract_ids_in_batch]

                    paid_schedules = list(
                        PaymentSchedule.objects.filter(
                            contract_id__in=contract_id_list,
                            status="PAID"
                        ).values("id", "contract_id", "installment_number", "total_amount", "late_fee", "late_days")
                    )

                    # Build lookup from contract_id to borrower/lender
                    contract_party = {c["id"]: (c["borrower_id"], c["lender_id"]) for c in contract_ids_in_batch}

                    txn_objs = []
                    paid_key_set = set(paid_schedule_keys)

                    for sch in paid_schedules:
                        key = (sch["contract_id"], sch["installment_number"])
                        if key not in paid_key_set:
                            continue

                        borrower_id, lender_id = contract_party.get(sch["contract_id"], (None, None))
                        if not borrower_id or not lender_id:
                            continue

                        txn_objs.append(
                            PaymentTransaction(
                                contract_id=sch["contract_id"],
                                payer_id=borrower_id,
                                recipient_id=lender_id,
                                payment_schedule_id=sch["id"],
                                amount=sch["total_amount"],
                                transaction_type="REPAYMENT",
                                payment_method=random.choice(["WALLET", "BANK"]),
                                status="SUCCESS",
                                late_fee=sch["late_fee"] or d2(0),
                                late_days=sch["late_days"] or 0,
                                transaction_ref=f"TXN-{sch['contract_id']}-{sch['installment_number']}-{random.randint(100000, 999999)}",
                                note="Mock repayment",
                            )
                        )

                    if txn_objs:
                        PaymentTransaction.objects.bulk_create(txn_objs, batch_size=batch_size)
                        txns_created += len(txn_objs)

                # ========== STEP H: Create Disputes for late contracts ==========
                # Always create disputes for some late contracts (not conditional on --create-disputes)
                if late_contract_ids:
                    late_list = list(late_contract_ids)
                    # Create disputes for ~15% of late contracts
                    pick_n = max(1, int(len(late_list) * 0.15))
                    picked = random.sample(late_list, k=min(pick_n, len(late_list)))

                    # Need to get borrower/lender for each contract
                    contract_party = {c["id"]: (c["borrower_id"], c["lender_id"]) for c in contract_rows}

                    dispute_objs = []
                    dispute_data_for_evidence = []  # Store data for creating evidence after dispute IDs are known

                    for cid in picked:
                        borrower_id, lender_id = contract_party.get(cid, (None, None))
                        if not borrower_id or not lender_id:
                            continue

                        # Pick random dispute type, but weight LATE_PAYMENT more heavily
                        if random.random() < 0.7:
                            d_type = "LATE_PAYMENT"
                        else:
                            d_type = random.choice(dispute_types)

                        # Pick status with weights (60% OPEN, 20% IN_REVIEW, 15% RESOLVED, 5% ESCALATED)
                        r = random.random()
                        if r < 0.60:
                            d_status = "OPEN"
                            resolved_at = None
                            resolution = None
                            resolution_type = None
                        elif r < 0.80:
                            d_status = "IN_REVIEW"
                            resolved_at = None
                            resolution = None
                            resolution_type = None
                        elif r < 0.95:
                            d_status = "RESOLVED"
                            resolved_at = timezone.now() - timedelta(days=random.randint(1, 30))
                            resolution = "Tranh chấp đã được giải quyết. Người vay đã thanh toán đầy đủ bao gồm phí trễ hạn."
                            resolution_type = random.choice(["PAYMENT_COMPLETED", "REFUND", "PENALTY"])
                        else:
                            d_status = "ESCALATED"
                            resolved_at = None
                            resolution = None
                            resolution_type = None

                        # Get late schedule info for this contract if available
                        late_info = next((info for info in late_schedule_info if info["contract_id"] == cid), None)
                        inst_num = late_info["installment_number"] if late_info else 1

                        description = dispute_descriptions[d_type].format(inst_num=inst_num)

                        # AI analysis and recommendation for some disputes
                        ai_analysis = None
                        ai_recommendation = None
                        if d_status in ("IN_REVIEW", "RESOLVED"):
                            ai_analysis = f"Phân tích AI: Hợp đồng #{cid} có {late_info['late_days'] if late_info else 'một số'} ngày trễ hạn. " \
                                          f"Lịch sử thanh toán cho thấy borrower có điểm tín dụng trung bình."
                            ai_recommendation = "Đề xuất: Áp dụng phí trễ hạn theo quy định và gửi nhắc nhở thanh toán."

                        penalty = d2(random.randint(50_000, 500_000)) if d_status == "RESOLVED" else d2(0)
                        refund = d2(random.randint(0, 100_000)) if d_status == "RESOLVED" and random.random() < 0.2 else d2(0)

                        dispute_objs.append(
                            Dispute(
                                contract_id=cid,
                                raised_by_id=lender_id,
                                complainant_id=lender_id,
                                respondent_id=borrower_id,
                                dispute_type=d_type,
                                description=description,
                                status=d_status,
                                penalty_amount=penalty,
                                refund_amount=refund,
                                resolution=resolution,
                                resolution_type=resolution_type,
                                ai_analysis=ai_analysis,
                                ai_recommendation=ai_recommendation,
                                resolution_notes="Ghi chú giải quyết mock." if d_status == "RESOLVED" else None,
                            )
                        )

                        # Store data for evidence creation
                        dispute_data_for_evidence.append({
                            "contract_id": cid,
                            "borrower_id": borrower_id,
                            "lender_id": lender_id,
                            "dispute_type": d_type,
                        })

                    if dispute_objs:
                        Dispute.objects.bulk_create(dispute_objs, batch_size=batch_size)
                        disputes_created += len(dispute_objs)

                        # ========== STEP I: Create DisputeEvidence for each dispute ==========
                        # Re-fetch disputes to get their IDs
                        dispute_contract_ids = [d["contract_id"] for d in dispute_data_for_evidence]
                        dispute_rows = list(
                            Dispute.objects.filter(contract_id__in=dispute_contract_ids)
                            .values("id", "contract_id", "raised_by_id")
                        )
                        dispute_by_contract = {r["contract_id"]: r for r in dispute_rows}

                        evidence_objs = []
                        evidence_types = ["TEXT", "IMAGE", "PDF", "OTHER"]

                        for d_data in dispute_data_for_evidence:
                            dispute_row = dispute_by_contract.get(d_data["contract_id"])
                            if not dispute_row:
                                continue

                            dispute_id = dispute_row["id"]
                            submitted_by_id = dispute_row["raised_by_id"]

                            # Create 1-3 evidences per dispute
                            num_evidences = random.randint(1, 3)
                            used_types = random.sample(evidence_types, k=min(num_evidences, len(evidence_types)))

                            for e_type in used_types:
                                evidence_objs.append(
                                    DisputeEvidence(
                                        dispute_id=dispute_id,
                                        submitted_by_id=submitted_by_id,
                                        evidence_type=e_type,
                                        description=evidence_descriptions[e_type],
                                        file=None,  # Mock data - no actual files
                                    )
                                )

                        if evidence_objs:
                            DisputeEvidence.objects.bulk_create(evidence_objs, batch_size=batch_size)
                            evidences_created += len(evidence_objs)

            # Progress report
            if total_created % (batch_size * 2) == 0 or total_created >= loans_target:
                self._progress(
                    f"Progress: loans={total_created}/{loans_target} | matches={matches_created} | "
                    f"contracts={contracts_created} | schedules={schedules_created} | rep_schedules={repayment_schedules_created} | "
                    f"txns={txns_created} | disputes={disputes_created} | evidences={evidences_created}"
                )

        self._progress(
            self.style.SUCCESS(
                f"Seed completed! loans={total_created}, matches={matches_created}, "
                f"contracts={contracts_created}, schedules={schedules_created}, rep_schedules={repayment_schedules_created}, "
                f"txns={txns_created}, disputes={disputes_created}, evidences={evidences_created}"
            )
        )

