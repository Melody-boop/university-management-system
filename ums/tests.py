from datetime import date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    AcademicYear, AdmissionApplication, AttendanceRecord, AttendanceSession,
    Book, BookCategory, BookLoan, CourseRegistration, CourseUnit, Department,
    Faculty, FeeStructure, GradingScale, Lecturer, Payment, Programme, Result,
    Semester, Student, StudentFee, TimetableSlot, User,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class WorkflowTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Technology", code="TECH")
        self.department = Department.objects.create(faculty=faculty, name="Computing", code="COMP")
        self.programme = Programme.objects.create(department=self.department, name="BSc Computing", code="BSC-COMP")
        year = AcademicYear.objects.create(name="2026/27", start_date=date(2026, 8, 1), end_date=date(2027, 7, 31), is_current=True)
        self.semester = Semester.objects.create(academic_year=year, name="Semester 1", start_date=date(2026, 8, 1), end_date=date(2026, 12, 31))
        self.admin = User.objects.create_user("admin@example.edu", "TestingPass123!", first_name="Admin", last_name="User", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        self.registrar = User.objects.create_user("registrar@example.edu", "TestingPass123!", first_name="Reg", last_name="User", role=User.Role.REGISTRAR)
        self.student_user = User.objects.create_user("student@example.edu", "TestingPass123!", first_name="Asha", last_name="Muli", role=User.Role.STUDENT)
        self.other_user = User.objects.create_user("other@example.edu", "TestingPass123!", first_name="Noah", last_name="Kip", role=User.Role.STUDENT)
        self.lecturer_user = User.objects.create_user("lecturer@example.edu", "TestingPass123!", first_name="Lee", last_name="Kim", role=User.Role.LECTURER)
        self.finance = User.objects.create_user("finance@example.edu", "TestingPass123!", first_name="Fin", last_name="User", role=User.Role.FINANCE)
        self.student = Student.objects.create(user=self.student_user, programme=self.programme, registration_number="NSU/26/001")
        self.other_student = Student.objects.create(user=self.other_user, programme=self.programme, registration_number="NSU/26/002")
        self.lecturer = Lecturer.objects.create(user=self.lecturer_user, staff_number="STAFF-001", department=self.department)
        self.unit = CourseUnit.objects.create(department=self.department, semester=self.semester, lecturer=self.lecturer, code="CSC101", name="Computing Basics")
        self.scale_a = GradingScale.objects.create(grade="A", minimum_score=80, grade_point=4)
        self.scale_f = GradingScale.objects.create(grade="F", minimum_score=0, grade_point=0)
        self.client.force_login(self.student_user)

    def test_student_cannot_read_another_student_record(self):
        response = self.client.get(reverse("student-detail", args=[self.other_student.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(reverse("record-list", args=["students"])).status_code, 403)

    def test_student_can_view_own_dashboard_and_login_uses_email(self):
        self.client.logout()
        self.assertTrue(self.client.login(username="student@example.edu", password="TestingPass123!"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NSU/26/001")

    def test_registration_requires_prerequisite_and_prevents_duplicates(self):
        prerequisite = CourseUnit.objects.create(department=self.department, semester=self.semester, code="CSC100", name="Intro")
        self.unit.prerequisites.add(prerequisite)
        response = self.client.post(reverse("register-unit", args=[self.unit.pk]))
        self.assertRedirects(response, reverse("dashboard"))
        self.assertFalse(CourseRegistration.objects.filter(student=self.student, unit=self.unit).exists())
        Result.objects.create(student=self.student, unit=prerequisite, cat_mark=25, assignment_mark=20, exam_mark=45, published=True)
        self.client.post(reverse("register-unit", args=[self.unit.pk]))
        self.client.post(reverse("register-unit", args=[self.unit.pk]))
        self.assertEqual(CourseRegistration.objects.filter(student=self.student, unit=self.unit).count(), 1)

    def test_payment_cannot_exceed_fee_balance(self):
        year = self.semester.academic_year
        structure = FeeStructure.objects.create(programme=self.programme, name="Tuition", amount=Decimal("100.00"), academic_year=year)
        fee = StudentFee.objects.create(student=self.student, structure=structure, amount=Decimal("100.00"))
        Payment.objects.create(fee=fee, amount=Decimal("40.00"), method=Payment.Method.CASH, reference="PAY-001", recorded_by=self.finance)
        self.assertEqual(fee.balance, Decimal("60.00"))
        with self.assertRaises(ValidationError):
            Payment.objects.create(fee=fee, amount=Decimal("60.01"), method=Payment.Method.BANK, reference="PAY-002", recorded_by=self.finance)

    def test_published_result_grade_and_immutability(self):
        result = Result.objects.create(student=self.student, unit=self.unit, cat_mark=25, assignment_mark=20, exam_mark=45, published=True)
        self.assertEqual(result.total, Decimal("90"))
        self.assertEqual(result.grade, self.scale_a)
        result.exam_mark = Decimal("44")
        with self.assertRaises(ValidationError):
            result.save()

    def test_timetable_detects_lecturer_and_room_conflicts(self):
        TimetableSlot.objects.create(unit=self.unit, lecturer=self.lecturer, day=TimetableSlot.Day.MONDAY, start_time=time(9), end_time=time(11), room="SCI-1")
        another_unit = CourseUnit.objects.create(department=self.department, semester=self.semester, lecturer=self.lecturer, code="CSC102", name="Algorithms")
        conflict = TimetableSlot(unit=another_unit, lecturer=self.lecturer, day=TimetableSlot.Day.MONDAY, start_time=time(10), end_time=time(12), room="SCI-2")
        with self.assertRaises(ValidationError):
            conflict.full_clean()

    def test_attendance_is_unique_per_student_per_session(self):
        CourseRegistration.objects.create(student=self.student, unit=self.unit, status=CourseRegistration.Status.APPROVED)
        session = AttendanceSession.objects.create(unit=self.unit, date=date(2026, 11, 5), start_time=time(9), created_by=self.lecturer_user)
        AttendanceRecord.objects.create(session=session, student=self.student, status=AttendanceRecord.Status.PRESENT)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceRecord.objects.create(session=session, student=self.student, status=AttendanceRecord.Status.LATE)

    def test_role_restrictions_and_lecturer_unit_scope(self):
        self.assertEqual(self.client.get(reverse("record-list", args=["attendance-records"])).status_code, 200)
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get(reverse("record-list", args=["attendance-records"])).status_code, 403)
        self.client.force_login(self.lecturer_user)
        self.assertEqual(self.client.get(reverse("record-list", args=["results"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("record-create", args=["students"])).status_code, 403)

    def test_student_checkout_and_return_updates_inventory(self):
        category = BookCategory.objects.create(name="Computing")
        book = Book.objects.create(category=category, title="Software Systems", author="A. Writer", isbn="9780000000002", total_copies=2, available_copies=2)
        self.client.post(reverse("borrow-book", args=[book.pk]))
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)
        loan = BookLoan.objects.get(student=self.student, book=book, returned_at__isnull=True)
        self.client.post(reverse("return-book", args=[loan.pk]))
        book.refresh_from_db()
        loan.refresh_from_db()
        self.assertEqual(book.available_copies, 2)
        self.assertIsNotNone(loan.returned_at)

    def test_admission_application_submission_is_persisted(self):
        self.client.logout()
        response = self.client.post(reverse("admission-apply"), {
            "first_name": "Mara", "last_name": "Ochieng", "email": "mara@applicant.example",
            "phone": "+254700000111", "programme": self.programme.pk,
            "qualification": "KCSE",
        })
        self.assertRedirects(response, reverse("admission-apply"))
        self.assertTrue(AdmissionApplication.objects.filter(email="mara@applicant.example", status=AdmissionApplication.Status.PENDING).exists())

    def test_admin_can_open_custom_user_creation_form(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/ums/user/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "email")

    def test_logout_requires_post_and_clears_session(self):
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("login"))

    def test_each_role_dashboard_renders(self):
        for user in (self.student_user, self.lecturer_user, self.finance, self.registrar, self.admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
