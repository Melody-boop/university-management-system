from django.contrib import admin
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm, UserCreationForm as BaseUserCreationForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    AcademicYear, AdmissionApplication, Announcement, AttendanceRecord, AttendanceSession,
    AuditLog, Book, BookCategory, BookLoan, CourseRegistration, CourseUnit, Department,
    Faculty, FeeStructure, GradingScale, Lecturer, Notification, Payment, Programme,
    Result, Semester, Student, StudentFee, TimetableSlot, User,
)


class UMSUserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "role")


class UMSUserChangeForm(BaseUserChangeForm):
    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UMSUserChangeForm
    add_form = UMSUserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = ((None, {"fields": ("email", "password")}), ("Personal information", {"fields": ("first_name", "last_name", "role")}), ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}), ("Important dates", {"fields": ("last_login", "date_joined")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "role", "password1", "password2", "is_staff", "is_superuser")}),)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("registration_number", "user", "programme", "year_of_study", "status")
    list_filter = ("status", "year_of_study", "programme__department")
    search_fields = ("registration_number", "user__first_name", "user__last_name", "user__email")


@admin.register(CourseUnit)
class CourseUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "department", "semester", "lecturer", "is_active")
    list_filter = ("department", "semester", "is_active")
    search_fields = ("code", "name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "fee", "amount", "method", "recorded_by", "paid_at")
    list_filter = ("method", "paid_at")
    search_fields = ("reference", "fee__student__registration_number")


@admin.register(AdmissionApplication)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "programme", "status", "submitted_at")
    list_filter = ("status", "programme")
    search_fields = ("first_name", "last_name", "email")


admin.site.register([
    AcademicYear, Announcement, AttendanceRecord, AttendanceSession, AuditLog, Book,
    BookCategory, BookLoan, CourseRegistration, Department, Faculty, FeeStructure,
    GradingScale, Lecturer, Notification, Programme, Result, Semester, StudentFee,
    TimetableSlot,
])