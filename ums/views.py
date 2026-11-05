import csv
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AdmissionForm, EmailAuthenticationForm, StudentProfileForm, record_form
from .models import (
    AcademicYear, AdmissionApplication, Announcement, AttendanceRecord, AttendanceSession,
    AuditLog, Book, BookCategory, BookLoan, CourseRegistration, CourseUnit, Department,
    Faculty, FeeStructure, GradingScale, Lecturer, Notification, Payment, Programme,
    Result, Semester, Student, StudentFee, TimetableSlot, User,
)

UserModel = get_user_model()

MODEL_REGISTRY = {
    "faculties": (Faculty, "Faculties", "academics"),
    "departments": (Department, "Departments", "academics"),
    "programmes": (Programme, "Programmes", "academics"),
    "academic-years": (AcademicYear, "Academic years", "academics"),
    "semesters": (Semester, "Semesters", "academics"),
    "units": (CourseUnit, "Academic units", "academics"),
    "lecturers": (Lecturer, "Lecturers", "people"),
    "students": (Student, "Students", "people"),
    "admissions": (AdmissionApplication, "Admission applications", "people"),
    "registrations": (CourseRegistration, "Unit registrations", "courses"),
    "grading-scales": (GradingScale, "Grading scales", "exams"),
    "results": (Result, "Examination results", "exams"),
    "fee-structures": (FeeStructure, "Fee structures", "finance"),
    "student-fees": (StudentFee, "Student fee accounts", "finance"),
    "payments": (Payment, "Payments", "finance"),
    "timetable": (TimetableSlot, "Timetable", "timetable"),
    "attendance-sessions": (AttendanceSession, "Attendance sessions", "attendance"),
    "attendance-records": (AttendanceRecord, "Attendance records", "attendance"),
    "book-categories": (BookCategory, "Book categories", "library"),
    "books": (Book, "Library catalogue", "library"),
    "book-loans": (BookLoan, "Book loans", "library"),
    "announcements": (Announcement, "Announcements", "communications"),
    "notifications": (Notification, "Notifications", "communications"),
    "audit-log": (AuditLog, "Audit log", "audit"),
}

MODULE_ACCESS = {
    "academics": {User.Role.ADMIN, User.Role.REGISTRAR, User.Role.STUDENT},
    "people": {User.Role.ADMIN, User.Role.REGISTRAR},
    "courses": {User.Role.ADMIN, User.Role.REGISTRAR},
    "exams": {User.Role.ADMIN, User.Role.REGISTRAR, User.Role.LECTURER},
    "finance": {User.Role.ADMIN, User.Role.FINANCE},
    "timetable": {User.Role.ADMIN, User.Role.REGISTRAR, User.Role.LECTURER, User.Role.STUDENT},
    "attendance": {User.Role.ADMIN, User.Role.LECTURER, User.Role.STUDENT},
    "library": {User.Role.ADMIN, User.Role.REGISTRAR, User.Role.STUDENT},
    "communications": set(User.Role.values),
    "audit": {User.Role.ADMIN},
}

MODULES = [
    ("academics", "Academic structure", "bi-diagram-3"),
    ("people", "Students & admissions", "bi-people"),
    ("courses", "Unit registration", "bi-journal-check"),
    ("exams", "Exams & results", "bi-mortarboard"),
    ("finance", "Finance", "bi-cash-coin"),
    ("timetable", "Timetable", "bi-calendar-week"),
    ("attendance", "Attendance", "bi-clipboard-check"),
    ("library", "Library", "bi-book"),
    ("communications", "Communications", "bi-megaphone"),
    ("audit", "Audit log", "bi-shield-check"),
]


class UMSLoginView(LoginView):
    template_name = "ums/login.html"
    authentication_form = EmailAuthenticationForm

    def form_valid(self, form):
        remember = self.request.POST.get("remember") == "on"
        self.request.session.set_expiry(60 * 60 * 24 * 14 if remember else 0)
        return super().form_valid(form)


def has_role(*roles):
    def check(user):
        return user.is_authenticated and (user.is_superuser or user.role in roles)
    return user_passes_test(check)


def _role_modules(user):
    return [item for item in MODULES if user.is_superuser or user.role in MODULE_ACCESS[item[0]]]


@login_required
def dashboard(request):
    user = request.user
    role = user.role
    modules = _role_modules(user)
    announcements = Announcement.objects.filter(is_published=True).filter(
        models_expired_filter()
    ).order_by("-published_at")[:5]
    counts = {
        "students": Student.objects.filter(status=Student.Status.ACTIVE).count(),
        "lecturers": Lecturer.objects.filter(is_active=True).count(),
        "departments": Department.objects.filter(is_active=True).count(),
        "programmes": Programme.objects.filter(is_active=True).count(),
        "units": CourseUnit.objects.filter(is_active=True).count(),
        "admissions": AdmissionApplication.objects.filter(status=AdmissionApplication.Status.PENDING).count(),
    }
    department_stats = list(Department.objects.annotate(student_count=Count("programmes__students")).values("name", "student_count").order_by("name")[:8])
    max_students = max((row["student_count"] for row in department_stats), default=1) or 1
    chart_rows = [{**row, "bar_width": max(3, round(row["student_count"] * 100 / max_students))} for row in department_stats]
    chart_labels = [row["name"] for row in department_stats]
    chart_values = [row["student_count"] for row in department_stats]
    context = {"modules": modules, "announcements": announcements, "counts": counts, "chart_labels": chart_labels, "chart_values": chart_values, "chart_rows": chart_rows, "now": timezone.localtime(), "today": timezone.localdate()}

    if role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)
        context["student"] = student
        if student:
            context["registrations"] = student.registrations.select_related("unit", "unit__semester").order_by("unit__code")[:8]
            context["results"] = student.results.filter(published=True).select_related("unit", "grade")[:8]
            context["balance"] = sum((fee.balance for fee in student.fees.all()), start=0)
            context["attendance_count"] = AttendanceRecord.objects.filter(student=student).count()
            context["available_units"] = CourseUnit.objects.filter(department=student.programme.department, is_active=True, semester__registration_open=True).exclude(registrations__student=student)
        else:
            context["registrations"] = []
            context["results"] = []
            context["balance"] = 0
            context["available_units"] = CourseUnit.objects.none()
    elif role == User.Role.LECTURER:
        lecturer = getattr(user, "lecturer_profile", None)
        context["my_units"] = lecturer.units.filter(is_active=True) if lecturer else CourseUnit.objects.none()
        context["pending_results"] = Result.objects.filter(unit__lecturer=lecturer, published=False).count() if lecturer else 0
    elif role == User.Role.FINANCE:
        context["collected"] = Payment.objects.aggregate(total=Sum("amount"))["total"] or 0
        context["outstanding"] = sum((fee.balance for fee in StudentFee.objects.select_related("student", "structure")), start=0)
        context["recent_payments"] = Payment.objects.select_related("fee__student__user").order_by("-paid_at")[:8]
    elif role == User.Role.REGISTRAR:
        context["pending_registrations"] = CourseRegistration.objects.filter(status=CourseRegistration.Status.PENDING).count()
        context["pending_admissions"] = AdmissionApplication.objects.filter(status=AdmissionApplication.Status.PENDING).count()
    else:
        context["collected"] = Payment.objects.aggregate(total=Sum("amount"))["total"] or 0
        context["pending_admissions"] = AdmissionApplication.objects.filter(status=AdmissionApplication.Status.PENDING).count()
        context["recent_payments"] = Payment.objects.select_related("fee__student__user").order_by("-paid_at")[:8]
    return render(request, "ums/dashboard.html", context)


def models_expired_filter():
    from django.db.models import Q
    return Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())


def admission_apply(request):
    if request.method == "POST":
        form = AdmissionForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save()
            messages.success(request, f"Application submitted. Your tracking reference is APP-{application.pk:06d}.")
            return redirect("admission-apply")
    else:
        form = AdmissionForm()
    return render(request, "ums/admission_form.html", {"form": form})


@login_required
def record_list(request, slug):
    if slug not in MODEL_REGISTRY:
        raise PermissionDenied
    model, title, module = MODEL_REGISTRY[slug]
    if not (request.user.is_superuser or request.user.role in MODULE_ACCESS[module]):
        raise PermissionDenied
    records = model.objects.all()
    if model is Notification:
        records = records.filter(user=request.user)
    if request.user.role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        if not student:
            raise PermissionDenied
        if model is BookLoan:
            records = records.filter(student__user=request.user)
        elif model is Notification:
            records = records.filter(user=request.user)
        elif model is CourseUnit:
            records = records.filter(department=student.programme.department, is_active=True)
        elif model is Programme:
            records = records.filter(pk=student.programme_id)
        elif model is TimetableSlot:
            records = records.filter(unit__registrations__student=student, unit__registrations__status=CourseRegistration.Status.APPROVED).distinct()
        elif model is AttendanceSession:
            records = records.filter(unit__registrations__student=student, unit__registrations__status=CourseRegistration.Status.APPROVED).distinct()
        elif model is AttendanceRecord:
            records = records.filter(student=student)
        elif model is Announcement:
            from django.db.models import Q
            records = records.filter(is_published=True).filter(models_expired_filter()).filter(Q(department__isnull=True) | Q(department=student.programme.department) | Q(unit__registrations__student=student)).distinct()
        elif model not in {Book, BookCategory}:
            raise PermissionDenied
    lecturer = getattr(request.user, "lecturer_profile", None) if request.user.role == User.Role.LECTURER else None
    if request.user.role == User.Role.LECTURER and not lecturer:
        raise PermissionDenied
    if lecturer:
        if model is CourseUnit:
            records = records.filter(lecturer=lecturer)
        elif model is CourseRegistration:
            records = records.filter(unit__lecturer=lecturer)
        elif model is Result:
            records = records.filter(unit__lecturer=lecturer)
        elif model is TimetableSlot:
            records = records.filter(lecturer=lecturer)
        elif model is AttendanceSession:
            records = records.filter(unit__lecturer=lecturer)
        elif model is AttendanceRecord:
            records = records.filter(session__unit__lecturer=lecturer)
        elif model is Announcement:
            records = records.filter(unit__lecturer=lecturer)
        else:
            raise PermissionDenied
    query = request.GET.get("q", "").strip()
    if query:
        searchable = [field for field in model._meta.fields if isinstance(field, (models.CharField, models.TextField, models.EmailField))]
        if searchable:
            from django.db.models import Q
            search_query = Q()
            for field in searchable:
                search_query |= Q(**{f"{field.name}__icontains": query})
            records = records.filter(search_query)
    records = records.select_related(*[field.name for field in model._meta.fields if isinstance(field, models.ForeignKey)][:3])[:100]
    fields = [field for field in model._meta.fields if field.name not in {"id", "password", "last_login", "user_permissions", "groups"}][:6]
    table_rows = []
    for record in records:
        values = []
        for field in fields:
            value = getattr(record, field.name)
            if field.choices:
                value = getattr(record, f"get_{field.name}_display")()
            elif isinstance(field, models.FileField):
                value = value.name.rsplit("/", 1)[-1] if value else "—"
            else:
                value = str(value) if value is not None else "—"
            values.append(value)
        table_rows.append((record, values))
    can_create = slug != "audit-log" and request.user.role != User.Role.STUDENT
    return render(request, "ums/record_list.html", {"title": title, "slug": slug, "records": records, "table_rows": table_rows, "fields": fields, "query": query, "can_create": can_create})


@login_required
def record_form(request, slug, pk=None):
    if slug not in MODEL_REGISTRY:
        raise PermissionDenied
    model, title, module = MODEL_REGISTRY[slug]
    if not (request.user.is_superuser or request.user.role in MODULE_ACCESS[module]):
        raise PermissionDenied
    if slug == "audit-log":
        raise PermissionDenied
    if request.user.role == User.Role.STUDENT:
        raise PermissionDenied
    if request.user.role == User.Role.STUDENT and model in {Announcement, Notification}:
        raise PermissionDenied
    if request.user.role == User.Role.LECTURER and model is Notification:
        raise PermissionDenied
    lecturer = getattr(request.user, "lecturer_profile", None) if request.user.role == User.Role.LECTURER else None
    if request.user.role == User.Role.LECTURER:
        lecturer_models = {Result, TimetableSlot, AttendanceSession, AttendanceRecord, Announcement}
        if not lecturer or model not in lecturer_models:
            raise PermissionDenied
    instance = get_object_or_404(model, pk=pk) if pk else None
    if model is User and not request.user.is_superuser:
        raise PermissionDenied
    exclude = []
    if model is Payment:
        exclude.extend(["recorded_by"])
    if model is Notification:
        if request.user.role not in {User.Role.ADMIN, User.Role.REGISTRAR}:
            raise PermissionDenied
        exclude.append("read_at")
    if model is AdmissionApplication:
        exclude.extend(["reviewer", "admission_number"])
    if model is Announcement and lecturer:
        exclude.extend(["author", "department"])
    if model is Result:
        exclude.extend(["grade"])
    if model is AttendanceSession:
        exclude.append("created_by")
    if lecturer and model is TimetableSlot:
        exclude.append("lecturer")
    if isinstance(instance, Result) and instance.published and lecturer:
        raise PermissionDenied
    Form = record_form(model, exclude=exclude)
    if lecturer and instance:
        assigned_unit = getattr(instance, "unit", None)
        if model is AttendanceRecord:
            assigned_unit = instance.session.unit
        if model is Result and assigned_unit.lecturer_id != lecturer.pk:
            raise PermissionDenied
        if model is TimetableSlot and instance.lecturer_id != lecturer.pk:
            raise PermissionDenied
        if model is AttendanceSession and assigned_unit.lecturer_id != lecturer.pk:
            raise PermissionDenied
        if model is AttendanceRecord and assigned_unit.lecturer_id != lecturer.pk:
            raise PermissionDenied
    if request.method == "POST":
        form = Form(request.POST, request.FILES, instance=instance)
    else:
        form = Form(instance=instance)
    if lecturer:
        if "unit" in form.fields:
            form.fields["unit"].queryset = CourseUnit.objects.filter(lecturer=lecturer)
        if "lecturer" in form.fields:
            form.fields["lecturer"].queryset = Lecturer.objects.filter(pk=lecturer.pk)
            form.fields["lecturer"].initial = lecturer
        if "session" in form.fields:
            form.fields["session"].queryset = AttendanceSession.objects.filter(unit__lecturer=lecturer)
        if "student" in form.fields:
            form.fields["student"].queryset = Student.objects.filter(registrations__unit__lecturer=lecturer, registrations__status=CourseRegistration.Status.APPROVED).distinct()
        if model is Announcement:
            form.fields["unit"].queryset = CourseUnit.objects.filter(lecturer=lecturer)
            form.fields["unit"].required = True
    if request.method == "POST":
        if form.is_valid():
            obj = form.save(commit=False)
            if isinstance(obj, Payment):
                obj.recorded_by = request.user
            if isinstance(obj, AttendanceSession):
                obj.created_by = request.user
            if isinstance(obj, AdmissionApplication):
                obj.reviewer = request.user
            if lecturer and isinstance(obj, Announcement):
                obj.author = request.user
                obj.department = obj.unit.department
            if lecturer and isinstance(obj, TimetableSlot):
                obj.lecturer = lecturer
            if isinstance(obj, AuditLog):
                raise PermissionDenied
            if isinstance(obj, Result) and instance and instance.published and request.user.role not in {User.Role.ADMIN, User.Role.REGISTRAR}:
                raise PermissionDenied
            if lecturer and isinstance(obj, Result) and not CourseRegistration.objects.filter(student=obj.student, unit=obj.unit, status=CourseRegistration.Status.APPROVED).exists():
                form.add_error(None, "Marks can only be entered for a student approved in this unit.")
                return render(request, "ums/record_form.html", {"form": form, "title": title, "slug": slug, "instance": instance})
            if isinstance(instance, Result) and instance.published and any(getattr(instance, name) != getattr(obj, name) for name in ("cat_mark", "assignment_mark", "exam_mark")):
                form.add_error(None, "Published results are locked and cannot be changed.")
                return render(request, "ums/record_form.html", {"form": form, "title": title, "slug": slug, "instance": instance})
            if isinstance(obj, BookLoan) and instance is None:
                from django.db import transaction
                with transaction.atomic():
                    book = Book.objects.select_for_update().get(pk=obj.book_id)
                    if book.available_copies < 1:
                        form.add_error("book", "No copies of this book are currently available.")
                        return render(request, "ums/record_form.html", {"form": form, "title": title, "slug": slug, "instance": instance})
                    obj.save()
                    book.available_copies -= 1
                    book.save(update_fields=["available_copies"])
            else:
                obj.save()
            form.save_m2m()
            if isinstance(obj, AdmissionApplication) and obj.status == AdmissionApplication.Status.APPROVED and not obj.admission_number:
                _approve_admission(obj, request.user)
            AuditLog.objects.create(actor=request.user, action="updated" if instance else "created", object_type=model.__name__, object_id=str(obj.pk))
            messages.success(request, f"{title[:-1] if title.endswith('s') else title} saved successfully.")
            return redirect("record-list", slug=slug)
    return render(request, "ums/record_form.html", {"form": form, "title": title, "slug": slug, "instance": instance})


def _approve_admission(application, actor):
    from django.db import transaction
    from django.utils.text import slugify
    with transaction.atomic():
        candidate = f"{slugify(application.first_name)}.{slugify(application.last_name)}"[:130]
        email = application.email.lower()
        user = UserModel.objects.filter(email=email).first()
        if not user:
            user = UserModel.objects.create_user(email=email, password=None, first_name=application.first_name, last_name=application.last_name, role=User.Role.STUDENT)
            user.set_unusable_password()
            user.save(update_fields=["password"])
        if not hasattr(user, "student_profile"):
            year = AcademicYear.objects.filter(is_current=True).first()
            Student.objects.create(user=user, registration_number=f"STU-{application.pk:06d}", programme=application.programme, admission_date=timezone.localdate())
        application.admission_number = f"ADM-{application.pk:06d}"
        application.save(update_fields=["admission_number"])
        Notification.objects.create(user=user, message=f"Your admission to {application.programme} has been approved.")
        AuditLog.objects.create(actor=actor, action="approved", object_type="AdmissionApplication", object_id=str(application.pk))


@login_required
def profile(request):
    student = getattr(request.user, "student_profile", None)
    if not student:
        return render(request, "ums/profile.html", {"student": None})
    if request.method == "POST":
        form = StudentProfileForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Your contact details were updated.")
            return redirect("profile")
    else:
        form = StudentProfileForm(instance=student)
    return render(request, "ums/profile.html", {"student": student, "form": form})


@login_required
def register_unit(request, unit_id):
    if request.user.role != User.Role.STUDENT:
        raise PermissionDenied
    student = get_object_or_404(Student, user=request.user)
    if student.status != Student.Status.ACTIVE:
        raise PermissionDenied
    unit = get_object_or_404(CourseUnit, pk=unit_id, is_active=True, department=student.programme.department, semester__registration_open=True)
    if request.method == "POST":
        if CourseRegistration.objects.filter(student=student, unit=unit).exists():
            messages.info(request, "You have already requested this unit.")
        else:
            completed = Result.objects.filter(student=student, unit__in=unit.prerequisites.all(), published=True, grade__grade_point__gt=0).values_list("unit_id", flat=True)
            missing = unit.prerequisites.exclude(pk__in=completed).exists()
            if missing:
                messages.error(request, "Complete the required prerequisite units before registering.")
            else:
                CourseRegistration.objects.create(student=student, unit=unit)
                messages.success(request, "Registration request sent for approval.")
        return redirect("dashboard")
    return render(request, "ums/register_unit.html", {"unit": unit})


@login_required
@has_role(User.Role.ADMIN, User.Role.REGISTRAR)
def approve_registration(request, pk):
    registration = get_object_or_404(CourseRegistration, pk=pk)
    if request.method == "POST":
        registration.status = request.POST.get("status") if request.POST.get("status") in {CourseRegistration.Status.APPROVED, CourseRegistration.Status.REJECTED} else CourseRegistration.Status.APPROVED
        registration.save(update_fields=["status"])
        AuditLog.objects.create(actor=request.user, action=registration.status, object_type="CourseRegistration", object_id=str(pk))
        messages.success(request, "Registration status updated.")
    return redirect("record-list", slug="registrations")


@login_required
@has_role(User.Role.ADMIN, User.Role.REGISTRAR)
def publish_result(request, pk):
    result = get_object_or_404(Result, pk=pk)
    if request.method == "POST":
        result.published = True
        result.save()
        AuditLog.objects.create(actor=request.user, action="published", object_type="Result", object_id=str(pk))
        messages.success(request, "Result published to the student portal.")
    return redirect("record-list", slug="results")


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.read_at = timezone.now()
    notification.save(update_fields=["read_at"])
    return redirect(notification.url or "dashboard")


@login_required
@require_POST
def borrow_book(request, pk):
    if request.user.role != User.Role.STUDENT:
        raise PermissionDenied
    from django.db import transaction
    student = get_object_or_404(Student, user=request.user)
    if student.status != Student.Status.ACTIVE:
        raise PermissionDenied
    with transaction.atomic():
        book = get_object_or_404(Book.objects.select_for_update(), pk=pk)
        if book.available_copies < 1:
            messages.error(request, "There are no available copies of this book.")
        elif BookLoan.objects.filter(student=student, book=book, returned_at__isnull=True).exists():
            messages.info(request, "You already have this book on loan.")
        else:
            from datetime import timedelta
            BookLoan.objects.create(book=book, student=student, due_date=timezone.localdate() + timedelta(days=14))
            book.available_copies -= 1
            book.save(update_fields=["available_copies"])
            AuditLog.objects.create(actor=request.user, action="borrowed", object_type="BookLoan", object_id=str(book.pk))
            messages.success(request, "Book checked out. Please return it by the due date.")
    return redirect("record-list", slug="books")


@login_required
@require_POST
def return_book(request, pk):
    from django.db import transaction
    loan = get_object_or_404(BookLoan.objects.select_related("book", "student__user"), pk=pk)
    if request.user.role == User.Role.STUDENT:
        if loan.student.user_id != request.user.pk:
            raise PermissionDenied
    elif request.user.role not in {User.Role.ADMIN, User.Role.REGISTRAR}:
        raise PermissionDenied
    if loan.returned_at is None:
        with transaction.atomic():
            loan.returned_at = timezone.localdate()
            loan.fine = loan.calculated_fine
            loan.save(update_fields=["returned_at", "fine"])
            book = Book.objects.select_for_update().get(pk=loan.book_id)
            book.available_copies = min(book.available_copies + 1, book.total_copies)
            book.save(update_fields=["available_copies"])
            AuditLog.objects.create(actor=request.user, action="returned", object_type="BookLoan", object_id=str(loan.pk))
        messages.success(request, f"Book returned. Fine assessed: KES {loan.fine}.")
    return redirect("record-list", slug="book-loans")


@login_required
def csv_report(request, slug):
    model_details = MODEL_REGISTRY.get(slug)
    if not model_details:
        raise PermissionDenied
    model, title, module = model_details
    if not (request.user.is_superuser or request.user.role in MODULE_ACCESS[module]):
        raise PermissionDenied
    rows = model.objects.all()
    if request.user.role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        if not student:
            raise PermissionDenied
        if model is BookLoan:
            rows = rows.filter(student=student)
        elif model is CourseUnit:
            rows = rows.filter(department=student.programme.department, is_active=True)
        elif model is Programme:
            rows = rows.filter(pk=student.programme_id)
        elif model is TimetableSlot:
            rows = rows.filter(unit__registrations__student=student, unit__registrations__status=CourseRegistration.Status.APPROVED).distinct()
        elif model is AttendanceSession:
            rows = rows.filter(unit__registrations__student=student, unit__registrations__status=CourseRegistration.Status.APPROVED).distinct()
        elif model is AttendanceRecord:
            rows = rows.filter(student=student)
        elif model is Announcement:
            from django.db.models import Q
            rows = rows.filter(is_published=True).filter(models_expired_filter()).filter(Q(department__isnull=True) | Q(department=student.programme.department) | Q(unit__registrations__student=student)).distinct()
        elif model not in {Book, BookCategory, Notification}:
            raise PermissionDenied
    if request.user.role == User.Role.LECTURER:
        lecturer = getattr(request.user, "lecturer_profile", None)
        if not lecturer:
            raise PermissionDenied
        if model is CourseUnit:
            rows = rows.filter(lecturer=lecturer)
        elif model in {Result, CourseRegistration}:
            rows = rows.filter(unit__lecturer=lecturer)
        elif model is TimetableSlot:
            rows = rows.filter(lecturer=lecturer)
        elif model is AttendanceSession:
            rows = rows.filter(unit__lecturer=lecturer)
        elif model is AttendanceRecord:
            rows = rows.filter(session__unit__lecturer=lecturer)
        elif model is Announcement:
            rows = rows.filter(unit__lecturer=lecturer)
        else:
            raise PermissionDenied
    if model is Notification:
        rows = rows.filter(user=request.user)
    rows = rows[:5000]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
    writer = csv.writer(response)
    fields = [field for field in model._meta.fields if field.concrete]
    writer.writerow([field.name for field in fields])
    for row in rows:
        writer.writerow([getattr(row, field.name) for field in fields])
    return response


@login_required
@has_role(User.Role.ADMIN, User.Role.FINANCE)
def finance_report(request):
    fees = StudentFee.objects.select_related("student__user", "structure")
    total_billed = fees.aggregate(total=Sum("amount"))["total"] or 0
    total_paid = Payment.objects.aggregate(total=Sum("amount"))["total"] or 0
    return render(request, "ums/finance_report.html", {"fees": fees[:250], "total_billed": total_billed, "total_paid": total_paid, "outstanding": total_billed - total_paid})


@login_required
def student_record(request, pk):
    if request.user.role == User.Role.STUDENT:
        student = get_object_or_404(Student, user=request.user)
        if student.pk != pk:
            raise PermissionDenied
    elif request.user.role == User.Role.FINANCE:
        student = get_object_or_404(Student, pk=pk)
    elif request.user.role in {User.Role.ADMIN, User.Role.REGISTRAR}:
        student = get_object_or_404(Student, pk=pk)
    else:
        raise PermissionDenied
    return render(request, "ums/student_detail.html", {"student": student, "fees": student.fees.select_related("structure"), "results": student.results.filter(published=True).select_related("unit", "grade"), "registrations": student.registrations.select_related("unit")})