from django.urls import path
from . import views

app_name = "lending"

urlpatterns = [
    # Borrower
    path("loan/create/", views.create_loan_request, name="create_loan"),
    path("loan/my/", views.my_loans, name="my_loans"),
    path("loan/<int:loan_id>/", views.loan_detail, name="loan_detail"),
    # Lender
    path("lender/profile/", views.lender_profile_view, name="lender_profile"),
    path("loans/browse/", views.browse_loans, name="browse_loans"),
    path("loan/<int:loan_id>/invest/", views.invest_in_loan, name="invest"),
    path("investments/", views.my_investments, name="my_investments"),
    # Payment
    path("payment/<int:schedule_id>/pay/", views.make_payment, name="make_payment"),
    # Dispute
    path(
        "contract/<int:contract_id>/dispute/",
        views.create_dispute,
        name="create_dispute",
    ),
    path("dispute/<int:dispute_id>/", views.dispute_detail, name="dispute_detail"),
    path("disputes/", views.my_disputes, name="my_disputes"),
]
