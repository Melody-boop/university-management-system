from decimal import Decimal
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("A superuser must have staff and superuser status")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "admin", "Super administrator"
        STUDENT = "student", "Student"
        LECTURER = "lecturer", "Lecturer"
        FINANCE = "finance", "Finance officer"
        REGISTRAR = "registrar", "Registrar / academic officer"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name


class Faculty(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=12, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Department(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT, related_name="departments")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=12, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Programme(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=20, unique=True)
    duration_years = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1), MaxValueValidator(12)])
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class AcademicYear(models.Model):
    name = models.CharField(max_length=30, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Semester(models.Model):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="semesters")
    name = models.CharField(max_length=30)
    start_date = models.DateField()
    end_date = models.DateField()
    registration_open = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["academic_year", "name"], name="unique_semester_per_year")]

    def __str__(self):
        return f"{self.academic_year} - {self.name}"


class Lecturer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="lecturer_profile")
    staff_number = models.CharField(max_length=24, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="lecturers")
    phone = models.CharField(max_length=24, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.staff_number} - {self.user.get_full_name()}"


class Student(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEFERRED = "deferred", "Deferred"
        GRADUATED = "graduated", "Graduated"
        SUSPENDED = "suspended", "Suspended"
        INACTIVE = "inactive", "Inactive"

    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"
        UNDISCLOSED = "undisclosed", "Prefer not to say"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    registration_number = models.CharField(max_length=24, unique=True, blank=True)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="students")
    year_of_study = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(12)])
    gender = models.CharField(max_length=12, choices=Gender.choices, default=Gender.UNDISCLOSED)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=24, blank=True)
    postal_address = models.CharField(max_length=240, blank=True)
    county = models.CharField(max_length=80, blank=True)
    admission_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    photo = models.ImageField(upload_to="students/", blank=True)

    class Meta:
        indexes = [models.Index(fields=["registration_number", "status"])]
        ordering = ["registration_number"]

    @property
    def department(self):
        return self.programme.department

    @property
    def gpa(self):
        results = self.results.filter(published=True, grade__isnull=False).select_related("grade", "unit")
        credits = sum(result.unit.credit_hours for result in results)
        return sum((result.grade.grade_point * result.unit.credit_hours for result in results), start=Decimal("0")) / credits if credits else Decimal("0")

    @property
    def attendance_percentage(self):
        records = self.attendance_records.all()
        total = records.count()
        attended = records.filter(status__in=["present", "late"]).count()
        return Decimal(attended * 100) / Decimal(total) if total else Decimal("0")

    def save(self, *args, **kwargs):
        if not self.registration_number:
            year = timezone.localdate().year
            while True:
                candidate = f"STU-{year}-{uuid.uuid4().hex[:6].upper()}"
                if not Student.objects.filter(registration_number=candidate).exists():
                    self.registration_number = candidate
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.registration_number} - {self.user.get_full_name()}"


class AdmissionApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEW = "review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField()
    phone = models.CharField(max_length=24)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="applications")
    qualification = models.CharField(max_length=180)
    document = models.FileField(upload_to="admissions/", blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    admission_number = models.CharField(max_length=24, unique=True, null=True, blank=True)
    reviewer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_applications")
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.programme}"


class CourseUnit(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="units")
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="units")
    lecturer = models.ForeignKey(Lecturer, null=True, blank=True, on_delete=models.SET_NULL, related_name="units")
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="required_for")
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    credit_hours = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(12)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class CourseRegistration(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DROPPED = "dropped", "Dropped"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="registrations")
    unit = models.ForeignKey(CourseUnit, on_delete=models.PROTECT, related_name="registrations")
    registered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "unit"], name="unique_student_unit_registration")]

    def __str__(self):
        return f"{self.student} - {self.unit}"


class GradingScale(models.Model):
    grade = models.CharField(max_length=4, unique=True)
    minimum_score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    grade_point = models.DecimalField(max_digits=3, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(4)])
    description = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-minimum_score"]

    def __str__(self):
        return self.grade


class Result(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="results")
    unit = models.ForeignKey(CourseUnit, on_delete=models.PROTECT, related_name="results")
    cat_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(30)])
    assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(20)])
    exam_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(50)])
    grade = models.ForeignKey(GradingScale, null=True, blank=True, on_delete=models.PROTECT)
    published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "unit"], name="unique_result_per_student_unit")]

    @property
    def total(self):
        return self.cat_mark + self.assignment_mark + self.exam_mark

    def save(self, *args, **kwargs):
        if self.pk:
            from django.core.exceptions import ValidationError
            old = Result.objects.get(pk=self.pk)
            if old.published and (not self.published or any(getattr(old, field) != getattr(self, field) for field in ("cat_mark", "assignment_mark", "exam_mark"))):
                raise ValidationError("Published results cannot be changed.")
        self.grade = GradingScale.objects.filter(minimum_score__lte=self.total).order_by("minimum_score").last()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.unit}: {self.total}"


class FeeStructure(models.Model):
    programme = models.ForeignKey(Programme, null=True, blank=True, on_delete=models.CASCADE, related_name="fee_structures")
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - KES {self.amount}"


class StudentFee(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="fees")
    structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="charges")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def amount_paid(self):
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def balance(self):
        return self.amount - self.amount_paid

    def __str__(self):
        return f"{self.student} - {self.structure.name}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        MPESA = "mpesa", "M-PESA (manual record)"

    fee = models.ForeignKey(StudentFee, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=12, choices=Method.choices)
    reference = models.CharField(max_length=80, unique=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payments")
    paid_at = models.DateTimeField(default=timezone.now)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fee_id:
            balance = self.fee.balance
            if self.pk:
                previous = Payment.objects.filter(pk=self.pk, fee_id=self.fee_id).values_list("amount", flat=True).first()
                if previous:
                    balance += previous
        else:
            balance = Decimal("0")
        if self.fee_id and self.amount > balance:
            raise ValidationError({"amount": "Payment cannot exceed the outstanding balance."})

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        from django.db import transaction
        with transaction.atomic():
            fee = StudentFee.objects.select_for_update().get(pk=self.fee_id)
            paid = fee.payments.exclude(pk=self.pk).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
            if self.amount > fee.amount - paid:
                raise ValidationError({"amount": "Payment cannot exceed the outstanding balance."})
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - KES {self.amount}"


class TimetableSlot(models.Model):
    class Day(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"

    unit = models.ForeignKey(CourseUnit, on_delete=models.CASCADE, related_name="timetable_slots")
    lecturer = models.ForeignKey(Lecturer, on_delete=models.PROTECT, related_name="timetable_slots")
    day = models.PositiveSmallIntegerField(choices=Day.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=40)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")
        conflicts = TimetableSlot.objects.filter(day=self.day, start_time__lt=self.end_time, end_time__gt=self.start_time)
        if self.pk:
            conflicts = conflicts.exclude(pk=self.pk)
        if conflicts.filter(lecturer=self.lecturer).exists():
            raise ValidationError({"lecturer": "Lecturer already has a class at this time."})
        if conflicts.filter(room__iexact=self.room).exists():
            raise ValidationError({"room": "Room is already booked at this time."})
        if conflicts.filter(unit=self.unit).exists():
            raise ValidationError({"unit": "This unit already has a class at this time."})

    def __str__(self):
        return f"{self.get_day_display()} {self.start_time} - {self.unit}"


class AttendanceSession(models.Model):
    unit = models.ForeignKey(CourseUnit, on_delete=models.CASCADE, related_name="attendance_sessions")
    date = models.DateField(default=timezone.localdate)
    start_time = models.TimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["unit", "date", "start_time"], name="unique_attendance_session")]

    def __str__(self):
        return f"{self.unit} - {self.date}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"

    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "student"], name="unique_attendance_per_session")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.session_id and self.student_id and not CourseRegistration.objects.filter(student=self.student, unit=self.session.unit, status=CourseRegistration.Status.APPROVED).exists():
            raise ValidationError({"student": "Student is not approved for this unit."})


class BookCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class Book(models.Model):
    category = models.ForeignKey(BookCategory, on_delete=models.PROTECT, related_name="books")
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=160)
    isbn = models.CharField(max_length=20, unique=True)
    total_copies = models.PositiveSmallIntegerField(default=1)
    available_copies = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"{self.title} ({self.isbn})"


class BookLoan(models.Model):
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="loans")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="book_loans")
    issued_at = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    returned_at = models.DateField(null=True, blank=True)
    fine = models.DecimalField(max_digits=9, decimal_places=2, default=0)

    @property
    def is_overdue(self):
        return self.returned_at is None and self.due_date < timezone.localdate()

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.pk and self.book_id and self.book.available_copies < 1:
            raise ValidationError({"book": "No copies of this book are currently available."})

    @property
    def calculated_fine(self):
        end_date = self.returned_at or timezone.localdate()
        overdue_days = max((end_date - self.due_date).days, 0)
        return Decimal(overdue_days) * settings.LIBRARY_DAILY_FINE

    def __str__(self):
        return f"{self.book} - {self.student}"


class Announcement(models.Model):
    title = models.CharField(max_length=180)
    body = models.TextField()
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.CASCADE, related_name="announcements")
    unit = models.ForeignKey(CourseUnit, null=True, blank=True, on_delete=models.CASCADE, related_name="announcements")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="announcements")
    published_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=240)
    url = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]