from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from ums.models import (
    AcademicYear, AdmissionApplication, Announcement, AttendanceRecord, AttendanceSession,
    Book, BookCategory, BookLoan, CourseRegistration, CourseUnit, Department,
    Faculty, FeeStructure, GradingScale, Lecturer, Payment, Programme, Result,
    Semester, Student, StudentFee, TimetableSlot, User,
)


class Command(BaseCommand):
    help = "Create fictional Northstar University demonstration records and role accounts."

    def handle(self, *args, **options):
        faculty, _ = Faculty.objects.get_or_create(code="SCI", defaults={"name": "Faculty of Science and Technology"})
        department, _ = Department.objects.get_or_create(code="COMP", defaults={"faculty": faculty, "name": "Department of Computing"})
        programme, _ = Programme.objects.get_or_create(code="BSC-CS", defaults={"department": department, "name": "BSc Computer Science", "duration_years": 4})
        year, _ = AcademicYear.objects.get_or_create(name="2026/2027", defaults={"start_date": date(2026, 8, 1), "end_date": date(2027, 7, 31), "is_current": True})
        year.is_current = True
        year.save(update_fields=["is_current"])
        semester, _ = Semester.objects.get_or_create(academic_year=year, name="Semester 1", defaults={"start_date": date(2026, 8, 1), "end_date": date(2026, 12, 20), "registration_open": True})

        accounts = {}
        account_specs = [
            ("admin@northstar.edu", "Amina", "Njoroge", User.Role.ADMIN, "NorthstarAdmin2026!", True),
            ("registrar@northstar.edu", "Peter", "Mwangi", User.Role.REGISTRAR, "NorthstarRegistrar2026!", False),
            ("lecturer@northstar.edu", "Grace", "Wanjiku", User.Role.LECTURER, "NorthstarLecturer2026!", False),
            ("finance@northstar.edu", "Daniel", "Otieno", User.Role.FINANCE, "NorthstarFinance2026!", False),
            ("student@northstar.edu", "Nia", "Kamau", User.Role.STUDENT, "NorthstarStudent2026!", False),
        ]
        for email, first, last, role, password, is_staff in account_specs:
            user, _ = User.objects.get_or_create(email=email, defaults={"first_name": first, "last_name": last, "role": role, "is_staff": is_staff, "is_superuser": role == User.Role.ADMIN})
            user.first_name, user.last_name, user.role, user.is_staff = first, last, role, is_staff
            if role == User.Role.ADMIN:
                user.is_superuser = True
            user.set_password(password)
            user.save()
            accounts[role] = user

        lecturer, _ = Lecturer.objects.get_or_create(user=accounts[User.Role.LECTURER], defaults={"staff_number": "NSU-STAFF-001", "department": department})
        student = self._student(accounts[User.Role.STUDENT], programme, "NSU/2026/0001")
        other_user = self._user("student2@northstar.edu", "Ibrahim", "Kariuki", User.Role.STUDENT)
        other_student = self._student(other_user, programme, "NSU/2026/0002")
        third_user = self._user("student3@northstar.edu", "Talia", "Muthoni", User.Role.STUDENT)
        third_student = self._student(third_user, programme, "NSU/2026/0003")

        units = []
        for code, name in [("CSC101", "Foundations of Computing"), ("CSC112", "Programming Methods"), ("MAT110", "Discrete Mathematics")]:
            unit, _ = CourseUnit.objects.get_or_create(code=code, defaults={"department": department, "semester": semester, "lecturer": lecturer, "name": name, "credit_hours": 3})
            units.append(unit)
        GradingScale.objects.get_or_create(grade="A", defaults={"minimum_score": 80, "grade_point": 4})
        GradingScale.objects.get_or_create(grade="B", defaults={"minimum_score": 70, "grade_point": 3})
        GradingScale.objects.get_or_create(grade="C", defaults={"minimum_score": 60, "grade_point": 2})
        GradingScale.objects.get_or_create(grade="D", defaults={"minimum_score": 50, "grade_point": 1})
        GradingScale.objects.get_or_create(grade="F", defaults={"minimum_score": 0, "grade_point": 0})
        for enrolled in (student, other_student, third_student):
            for unit in units:
                CourseRegistration.objects.get_or_create(student=enrolled, unit=unit, defaults={"status": CourseRegistration.Status.APPROVED})
        for enrolled in (student, other_student):
            Result.objects.get_or_create(student=enrolled, unit=units[0], defaults={"cat_mark": 24, "assignment_mark": 18, "exam_mark": 45, "published": True})

        fee_structure, _ = FeeStructure.objects.get_or_create(programme=programme, name="Tuition · Semester 1", academic_year=year, defaults={"amount": Decimal("85000.00")})
        for enrolled in (student, other_student, third_student):
            fee, _ = StudentFee.objects.get_or_create(student=enrolled, structure=fee_structure, defaults={"amount": Decimal("85000.00"), "due_date": date(2026, 10, 31)})
            if enrolled == student:
                Payment.objects.get_or_create(fee=fee, reference="NSU-DEMO-PAY-001", defaults={"amount": Decimal("50000.00"), "method": Payment.Method.MPESA, "recorded_by": accounts[User.Role.FINANCE]})

        TimetableSlot.objects.get_or_create(unit=units[0], day=TimetableSlot.Day.MONDAY, start_time=time(9), defaults={"end_time": time(11), "room": "SCI-204", "lecturer": lecturer})
        session, _ = AttendanceSession.objects.get_or_create(unit=units[0], date=timezone.localdate() - timedelta(days=1), start_time=time(9), defaults={"created_by": lecturer.user})
        for enrolled in (student, other_student, third_student):
            AttendanceRecord.objects.get_or_create(session=session, student=enrolled, defaults={"status": AttendanceRecord.Status.PRESENT})

        category, _ = BookCategory.objects.get_or_create(name="Computing")
        book, _ = Book.objects.get_or_create(isbn="9780000000001", defaults={"category": category, "title": "Principles of Software Design", "author": "M. K. Njeri", "total_copies": 6, "available_copies": 6})
        active_loan = BookLoan.objects.filter(book=book, student=other_student, returned_at__isnull=True).first()
        if not active_loan and book.available_copies:
            BookLoan.objects.create(book=book, student=other_student, due_date=timezone.localdate() + timedelta(days=7))
            book.available_copies -= 1
            book.save(update_fields=["available_copies"])

        Announcement.objects.get_or_create(title="Semester one is underway", defaults={"body": "Welcome to the new academic year. Check your timetable and confirm your unit registrations.", "author": accounts[User.Role.ADMIN]})
        AdmissionApplication.objects.get_or_create(email="zuri.maina@applicant.example", defaults={"first_name": "Zuri", "last_name": "Maina", "phone": "+254700000099", "programme": programme, "qualification": "Kenya Certificate of Secondary Education", "status": AdmissionApplication.Status.PENDING})
        self.stdout.write(self.style.SUCCESS("Northstar demo data is ready."))
        self.stdout.write("Demo accounts (email / password):")
        for email, _, _, _, password, _ in account_specs:
            self.stdout.write(f"  {email} / {password}")

    @staticmethod
    def _user(email, first_name, last_name, role):
        return User.objects.get_or_create(email=email, defaults={"first_name": first_name, "last_name": last_name, "role": role})[0]

    @staticmethod
    def _student(user, programme, registration_number):
        return Student.objects.get_or_create(user=user, defaults={"registration_number": registration_number, "programme": programme, "year_of_study": 1, "gender": Student.Gender.UNDISCLOSED})[0]