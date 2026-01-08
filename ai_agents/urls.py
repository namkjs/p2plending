from django.urls import path
from . import views

app_name = "ai_agents"

urlpatterns = [
    path("logs/", views.agent_logs_view, name="logs"),
    path("profiler/run/", views.run_borrower_profiler, name="run_profiler"),
    path("matcher/<int:loan_id>/run/", views.run_lender_matcher, name="run_matcher"),
    path("matcher/<int:loan_id>/matches/", views.get_matches, name="get_matches"),
    path("loan/<int:loan_id>/approve/", views.approve_loan, name="approve_loan"),
    path("payment/check/", views.run_payment_check, name="run_payment_check"),
    path("chat/send/", views.chat_send, name="chat_send"),
    path("chat/history/", views.chat_history, name="chat_history"),

]
