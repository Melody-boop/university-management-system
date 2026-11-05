from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.UMSLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password-change/", auth_views.PasswordChangeView.as_view(template_name="ums/password_form.html"), name="password_change"),
    path("password-change/done/", auth_views.PasswordChangeDoneView.as_view(template_name="ums/password_done.html"), name="password_change_done"),
    path("password-reset/", auth_views.PasswordResetView.as_view(template_name="ums/password_reset.html", email_template_name="ums/password_reset_email.html", subject_template_name="ums/password_reset_subject.txt", success_url="/password-reset/done/"), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="ums/password_done.html"), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="ums/password_reset_confirm.html", success_url="/login/"), name="password_reset_confirm"),
    path("admissions/apply/", views.admission_apply, name="admission-apply"),
    path("profile/", views.profile, name="profile"),
    path("students/<int:pk>/", views.student_record, name="student-detail"),
    path("units/<int:unit_id>/register/", views.register_unit, name="register-unit"),
    path("library/books/<int:pk>/borrow/", views.borrow_book, name="borrow-book"),
    path("library/loans/<int:pk>/return/", views.return_book, name="return-book"),
    path("registrations/<int:pk>/decision/", views.approve_registration, name="approve-registration"),
    path("results/<int:pk>/publish/", views.publish_result, name="publish-result"),
    path("notifications/<int:pk>/read/", views.mark_notification_read, name="notification-read"),
    path("reports/finance/", views.finance_report, name="finance-report"),
    path("reports/export/<slug:slug>/", views.csv_report, name="csv-report"),
    path("records/<slug:slug>/", views.record_list, name="record-list"),
    path("records/<slug:slug>/new/", views.record_form, name="record-create"),
    path("records/<slug:slug>/<int:pk>/edit/", views.record_form, name="record-edit"),
]