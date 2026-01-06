from django.urls import path
from . import views

app_name = "user"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("profile/", views.profile_view, name="profile"),
    path("kyc/", views.kyc_view, name="kyc"),
    path("kyc/upload/", views.upload_kyc_document, name="kyc_upload"),
    path("kyc/submit/", views.submit_kyc, name="kyc_submit"),
    path("notifications/", views.notifications_view, name="notifications"),
    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/deposit/", views.deposit, name="deposit"),
    path("wallet/withdraw/", views.withdraw, name="withdraw"),
]
