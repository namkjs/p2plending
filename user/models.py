from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # --- Thông tin chung (Ví tiền dùng chung cho cả Vay và Cho vay) ---
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # --- Thông tin định danh (User tự nhập vào Form) ---
    full_name = models.CharField(max_length=100, blank=True, verbose_name="Họ và tên")
    id_card_number = models.CharField(max_length=20, blank=True, verbose_name="Số CCCD")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Ngày sinh")
    gender = models.CharField(
        max_length=10,
        blank=True,
        choices=[
            ("male", "Nam"),
            ("female", "Nữ"),
        ],
        verbose_name="Giới tính",
    )
    hometown = models.CharField(max_length=255, blank=True, verbose_name="Quê quán")
    address = models.CharField(
        max_length=255, blank=True, verbose_name="Địa chỉ thường trú"
    )

    # --- Thông tin tài chính ---
    occupation = models.CharField(
        max_length=100, blank=True, verbose_name="Nghề nghiệp"
    )
    company_name = models.CharField(
        max_length=200, blank=True, verbose_name="Tên công ty"
    )
    monthly_income = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Thu nhập hàng tháng",
    )

    # --- Thông tin liên hệ ---
    phone_number = models.CharField(
        max_length=15, blank=True, verbose_name="Số điện thoại"
    )

    # --- Trạng thái KYC ---
    KYC_STATUS_CHOICES = [
        ("UNVERIFIED", "Chưa xác thực"),
        ("PENDING", "Đang chờ AI duyệt"),
        ("VERIFIED", "Đã xác thực"),
        ("REJECTED", "Bị từ chối"),
    ]
    kyc_status = models.CharField(
        max_length=20, choices=KYC_STATUS_CHOICES, default="UNVERIFIED"
    )

    # Lý do từ chối (nếu có) để hiện cho user sửa
    kyc_note = models.TextField(blank=True, null=True)

    # --- Dữ liệu OCR từ CCCD ---
    ocr_data = models.JSONField(
        null=True, blank=True, verbose_name="Dữ liệu OCR từ CCCD"
    )
    ocr_verified = models.BooleanField(default=False, verbose_name="Đã verify OCR")
    ocr_match_score = models.FloatField(
        null=True, blank=True, verbose_name="Điểm khớp OCR (%)"
    )

    def __str__(self):
        return f"{self.user.username} - {self.kyc_status}"


class KYCDocument(models.Model):
    """Lưu ảnh user upload để AI đọc"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="kyc_docs")
    image = models.ImageField(upload_to="kyc_images/")

    DOC_TYPE_CHOICES = [
        ("ID_CARD_FRONT", "CCCD Mặt trước"),
        ("ID_CARD_BACK", "CCCD Mặt sau"),
        ("SALARY_SLIP", "Bảng lương/Sao kê"),
    ]
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Kết quả AI đọc được lưu vào đây để đối chiếu sau này (Audit log)
    ai_extracted_data = models.JSONField(null=True, blank=True)
    ocr_status = models.CharField(
        max_length=20,
        default="PENDING",
        choices=[
            ("PENDING", "Chờ xử lý"),
            ("PROCESSING", "Đang xử lý"),
            ("SUCCESS", "Thành công"),
            ("FAILED", "Thất bại"),
        ],
    )
