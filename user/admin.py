from django.contrib import admin
from .models import UserProfile, KYCDocument


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "full_name", "kyc_status", "balance", "id_card_number"]
    list_filter = ["kyc_status"]
    search_fields = ["user__username", "full_name", "id_card_number"]
    readonly_fields = ["user"]

    fieldsets = (
        (
            "Thông tin User",
            {"fields": ("user", "full_name", "id_card_number", "address")},
        ),
        ("Tài chính", {"fields": ("balance",)}),
        ("KYC", {"fields": ("kyc_status", "kyc_note")}),
    )


@admin.register(KYCDocument)
class KYCDocumentAdmin(admin.ModelAdmin):
    list_display = ["user", "doc_type", "uploaded_at"]
    list_filter = ["doc_type", "uploaded_at"]
    search_fields = ["user__username"]
    readonly_fields = ["uploaded_at", "ai_extracted_data"]
