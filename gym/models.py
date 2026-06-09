"""
GYMKHANA — Models (Multi-Tenant SQL Schema)

MULTI-TENANCY:
  Every gym owner gets an isolated Gym (tenant). Every data row carries a
  `gym` FK. A UserProfile links each Django User to exactly one Gym, so two
  different gym owners NEVER see each other's members, payments, etc.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    class relativedelta:
        def __init__(self, months=0): self.months = months
        def __radd__(self, other):
            import calendar
            m = other.month + self.months - 1
            y = other.year + m // 12
            m = m % 12 + 1
            d = min(other.day, calendar.monthrange(y, m)[1])
            return other.replace(year=y, month=m, day=d)


# ═══════════════════════════════════════════════════════════════
#  GYM  (the tenant)
# ═══════════════════════════════════════════════════════════════
class Gym(models.Model):
    name           = models.CharField(max_length=120, default="My Gym")
    tagline        = models.CharField(max_length=200, blank=True)
    address        = models.TextField(blank=True)
    city           = models.CharField(max_length=80, blank=True)
    phone          = models.CharField(max_length=20, blank=True)
    whatsapp       = models.CharField(max_length=20, blank=True)
    email          = models.EmailField(blank=True)
    bank_name      = models.CharField(max_length=80, blank=True)
    bank_account   = models.CharField(max_length=30, blank=True)
    easypaisa_no   = models.CharField(max_length=15, blank=True)
    jazzcash_no    = models.CharField(max_length=15, blank=True)
    currency       = models.CharField(max_length=8, default="Rs.")
    currency_code  = models.CharField(max_length=4, default="PKR")
    gents_timing   = models.CharField(max_length=80, blank=True)
    ladies_timing  = models.CharField(max_length=80, blank=True)
    THEME_CHOICES  = [
        ('light','Light (Classic Orange)'),
        ('sage','Sage Green'),
        ('olive','Olive Green'),
        ('ocean','Ocean Blue'),
        ('charcoal','Charcoal (Dark)'),
    ]
    theme          = models.CharField(max_length=12, choices=THEME_CHOICES, default='light')
    owner_key      = models.CharField(max_length=4, default='0000',
                        help_text="4-digit PIN required to switch into Owner mode")
    # ── Platform subscription (managed by the software provider) ──
    SUB_STATUS = [('trial','Trial'),('active','Active'),('expired','Expired'),('suspended','Suspended')]
    subscription_status = models.CharField(max_length=10, choices=SUB_STATUS, default='trial')
    subscription_until  = models.DateField(null=True, blank=True,
                            help_text="Access is blocked after this date until renewed")
    subscription_fee    = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                            help_text="Monthly subscription fee charged to this gym")
    subscription_notes  = models.TextField(blank=True)
    owner          = models.ForeignKey(User, on_delete=models.CASCADE,
                        related_name='owned_gyms', null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def currency_symbol(self):
        from .currencies import symbol_for
        return symbol_for(self.currency_code)

    @property
    def subscription_active(self):
        from datetime import date as _d
        if self.subscription_status == 'suspended':
            return False
        if self.subscription_until and self.subscription_until < _d.today():
            return False
        return True


class UserProfile(models.Model):
    """Links a Django User to a Gym (tenant). One profile per user."""
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    gym         = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='staff')
    is_owner    = models.BooleanField(default=False)
    role        = models.CharField(max_length=40, default='staff')
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} @ {self.gym.name}"


# Abstract base: every tenant-scoped model inherits this
class TenantModel(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE)
    class Meta:
        abstract = True


# ═══════════════════════════════════════════════════════════════
#  MEMBERSHIP PLANS
# ═══════════════════════════════════════════════════════════════
class MembershipPlan(TenantModel):
    DURATION_CHOICES = [
        (0,'Custom / Daily'),(1,'Monthly (1 Month)'),(3,'Quarterly (3 Months)'),
        (6,'Half-Yearly (6 Months)'),(12,'Annual (12 Months)'),
    ]
    name             = models.CharField(max_length=80)
    duration         = models.PositiveSmallIntegerField(choices=DURATION_CHOICES, default=1)
    custom_days      = models.PositiveIntegerField(null=True, blank=True)
    price            = models.DecimalField(max_digits=10, decimal_places=2)
    description      = models.TextField(blank=True)
    is_active        = models.BooleanField(default=True)
    includes_cardio  = models.BooleanField(default=False, verbose_name="Includes Cardio/Treadmill")
    includes_weights = models.BooleanField(default=True,  verbose_name="Includes Free Weights")
    includes_trainer = models.BooleanField(default=False, verbose_name="Includes Personal Trainer")
    includes_locker  = models.BooleanField(default=False, verbose_name="Includes Locker")
    includes_steam   = models.BooleanField(default=False, verbose_name="Includes Steam Room")
    notes            = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['duration','price']

    def __str__(self):
        return f"{self.name} — Rs.{self.price}"


# ═══════════════════════════════════════════════════════════════
#  ADD-ONS
# ═══════════════════════════════════════════════════════════════
class AddOn(TenantModel):
    ADDON_TYPE = [
        ('trainer','Personal Trainer Sessions'),('cardio','Cardio / Electronic Equipment'),
        ('locker','Locker Rental'),('steam','Steam Room Access'),
        ('supplement','Supplements Package'),('gloves','Gloves / Belt / Wraps'),
        ('parking','Parking'),('custom','Custom'),
    ]
    BILLING_CYCLE = [('monthly','Per Month'),('session','Per Session'),('daily','Per Day'),('one_time','One-Time')]
    name          = models.CharField(max_length=100)
    addon_type    = models.CharField(max_length=15, choices=ADDON_TYPE, default='custom')
    price         = models.DecimalField(max_digits=8, decimal_places=2)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE, default='monthly')
    description   = models.TextField(blank=True)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['addon_type','name']

    def __str__(self):
        return f"{self.name} (Rs.{self.price}/{self.get_billing_cycle_display()})"


# ═══════════════════════════════════════════════════════════════
#  EMPLOYEES
# ═══════════════════════════════════════════════════════════════
class Employee(TenantModel):
    ROLE_CHOICES = [
        ('manager','Manager'),('trainer','Trainer / Coach'),('receptionist','Receptionist'),
        ('cleaner','Cleaner / Janitor'),('security','Security Guard'),
        ('accountant','Accountant'),('other','Other'),
    ]
    STATUS_CHOICES = [('active','Active'),('on_leave','On Leave'),('terminated','Terminated')]
    full_name        = models.CharField(max_length=150)
    phone            = models.CharField(max_length=15)
    email            = models.EmailField(blank=True)
    cnic             = models.CharField(max_length=15, blank=True, verbose_name="CNIC",
                         help_text="13-digit CNIC e.g. 42301-1234567-1")
    address          = models.TextField(blank=True)
    date_of_birth    = models.DateField(null=True, blank=True)
    blood_group      = models.CharField(max_length=5, blank=True)
    photo            = models.ImageField(upload_to='employee_photos/', blank=True, null=True)
    role             = models.CharField(max_length=15, choices=ROLE_CHOICES, default='trainer')
    status           = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active')
    join_date        = models.DateField(default=date.today)
    termination_date = models.DateField(null=True, blank=True)
    monthly_salary   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    salary_day       = models.PositiveSmallIntegerField(default=1)
    emergency_name   = models.CharField(max_length=100, blank=True)
    emergency_phone  = models.CharField(max_length=15, blank=True)
    emergency_relation = models.CharField(max_length=50, blank=True)
    specialization   = models.CharField(max_length=200, blank=True,
                         help_text="e.g. Weight Training, Cardio, CrossFit, Yoga")
    certifications   = models.TextField(blank=True)
    experience_years = models.PositiveSmallIntegerField(default=0)
    per_session_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes            = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['role','full_name']
        unique_together = ('gym','phone')

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    @property
    def is_trainer(self):
        return self.role == 'trainer'


class EmployeeAttendance(TenantModel):
    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance')
    date           = models.DateField(default=date.today)
    is_present     = models.BooleanField(default=True)
    check_in_time  = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    notes          = models.CharField(max_length=200, blank=True)
    marked_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee','date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee.full_name} — {self.date}"


class EmployeeSalaryPayment(TenantModel):
    METHOD_CHOICES = [('cash','Cash'),('easypaisa','EasyPaisa'),('jazzcash','JazzCash'),('bank','Bank Transfer'),('other','Other')]
    employee       = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    month          = models.DateField(help_text="First day of the salary month")
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    bonus          = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    deduction      = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    net_amount     = models.DecimalField(max_digits=10, decimal_places=2)
    method         = models.CharField(max_length=12, choices=METHOD_CHOICES, default='cash')
    paid_date      = models.DateField(default=date.today)
    transaction_id = models.CharField(max_length=60, blank=True)
    notes          = models.TextField(blank=True)
    paid_by        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_date']
        unique_together = ('employee','month')

    def save(self, *args, **kwargs):
        self.net_amount = self.amount + self.bonus - self.deduction
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.full_name} — {self.month.strftime('%b %Y')}"


# ═══════════════════════════════════════════════════════════════
#  LOCKERS
# ═══════════════════════════════════════════════════════════════
class Locker(TenantModel):
    STATUS_CHOICES = [('available','Available'),('occupied','Occupied'),('maintenance','Under Maintenance'),('reserved','Reserved')]
    ZONE_CHOICES   = [('gents','Gents Zone'),('ladies','Ladies Zone'),('shared','Shared/Common')]
    locker_number  = models.CharField(max_length=10)
    zone           = models.CharField(max_length=8, choices=ZONE_CHOICES, default='gents')
    monthly_rate   = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                       help_text="Monthly rental fee (0 if included in plan)")
    status         = models.CharField(max_length=12, choices=STATUS_CHOICES, default='available')
    notes          = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['zone','locker_number']
        unique_together = ('gym','locker_number')

    def __str__(self):
        return f"Locker {self.locker_number} ({self.get_zone_display()})"

    @property
    def current_assignment(self):
        return self.assignments.filter(is_active=True).first()

    @property
    def occupant(self):
        a = self.current_assignment
        return a.member if a else None

    @property
    def display_status(self):
        """Single source of truth for display: an active assignment always means
        occupied; otherwise honour maintenance/reserved; else available."""
        if self.assignments.filter(is_active=True).exists():
            return 'occupied'
        if self.status in ('maintenance', 'reserved'):
            return self.status
        return 'available'


class LockerAssignment(TenantModel):
    locker        = models.ForeignKey(Locker, on_delete=models.CASCADE, related_name='assignments')
    member        = models.ForeignKey('Member', on_delete=models.CASCADE, related_name='locker_assignments')
    assigned_date = models.DateField(default=date.today)
    expiry_date   = models.DateField(null=True, blank=True)
    monthly_rate  = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    amount_paid   = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                       help_text="Locker fee actually paid. Locker is assigned only when this covers the rate.")
    deposit_paid  = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    key_number    = models.CharField(max_length=20, blank=True)
    is_active     = models.BooleanField(default=True)
    released_date = models.DateField(null=True, blank=True)
    notes         = models.CharField(max_length=200, blank=True)
    assigned_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-assigned_date']

    def __str__(self):
        return f"Locker {self.locker.locker_number} -> {self.member.full_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep the parent locker's status in sync with this assignment.
        if self.locker_id:
            if self.is_active:
                if self.locker.status != 'occupied':
                    self.locker.status = 'occupied'
                    self.locker.save(update_fields=['status'])
            else:
                # released: free the locker only if no other active assignment exists
                still_busy = self.locker.assignments.filter(is_active=True).exclude(pk=self.pk).exists()
                if not still_busy and self.locker.status == 'occupied':
                    self.locker.status = 'available'
                    self.locker.save(update_fields=['status'])


# ═══════════════════════════════════════════════════════════════
#  MEMBER
# ═══════════════════════════════════════════════════════════════
class Member(TenantModel):
    SHIFT_CHOICES = [('gents','Gents Timing'),('ladies','Ladies Timing'),('open','Open / Both')]
    BLOOD_GROUP_CHOICES = [('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-'),('unknown','Unknown')]
    STATUS_CHOICES = [('active','Active'),('expired','Expired'),('suspended','Suspended'),('pending','Pending Approval'),('freeze','Membership Frozen'),('left','Left / Former Member')]

    full_name          = models.CharField(max_length=150)
    phone              = models.CharField(max_length=15)
    email              = models.EmailField(blank=True)
    cnic               = models.CharField(max_length=15, blank=True, verbose_name="CNIC / Form-B",
                           help_text="CNIC: 42301-1234567-1  |  Form-B for minors")
    date_of_birth      = models.DateField(null=True, blank=True)
    gender             = models.CharField(max_length=10, choices=[('male','Male'),('female','Female'),('other','Other')], default='male')
    blood_group        = models.CharField(max_length=8, choices=BLOOD_GROUP_CHOICES, default='unknown')
    address            = models.TextField(blank=True)
    city               = models.CharField(max_length=80, blank=True)
    photo              = models.ImageField(upload_to='member_photos/', blank=True, null=True)
    occupation         = models.CharField(max_length=100, blank=True)
    emergency_name     = models.CharField(max_length=100, blank=True)
    emergency_phone    = models.CharField(max_length=15, blank=True)
    emergency_relation = models.CharField(max_length=50, blank=True)
    medical_conditions = models.TextField(blank=True, help_text="Diabetes, BP, cardiac issues, injuries, etc.")
    fitness_goal       = models.CharField(max_length=200, blank=True)
    shift              = models.CharField(max_length=8, choices=SHIFT_CHOICES, default='gents')
    status             = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    join_date          = models.DateField(default=date.today)
    referred_by        = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                           related_name='referrals', verbose_name="Referred By (Member)")
    assigned_trainer   = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                           related_name='trainees', limit_choices_to={'role':'trainer','status':'active'})
    notes              = models.TextField(blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)
    registered_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='registered_members')
    left_date          = models.DateField(null=True, blank=True)
    left_reason        = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-join_date','full_name']
        unique_together = ('gym','phone')
        indexes = [models.Index(fields=['gym','phone']), models.Index(fields=['gym','status']), models.Index(fields=['cnic'])]

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

    @property
    def active_membership(self):
        return self.memberships.filter(status='active', end_date__gte=date.today()).first()

    @property
    def active_locker(self):
        return self.locker_assignments.filter(is_active=True).first()

    @property
    def is_fee_overdue(self):
        mem = self.active_membership
        return not mem or mem.end_date < date.today()

    @property
    def days_until_expiry(self):
        mem = self.active_membership
        return (mem.end_date - date.today()).days if mem else None


# ═══════════════════════════════════════════════════════════════
#  MEMBERSHIP RECORD
# ═══════════════════════════════════════════════════════════════
class MembershipRecord(TenantModel):
    STATUS_CHOICES = [('active','Active'),('expired','Expired'),('cancelled','Cancelled'),('frozen','Frozen')]
    member               = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='memberships')
    plan                 = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, related_name='records', null=True, blank=True)
    custom_plan_name     = models.CharField(max_length=120, blank=True, help_text="Name for custom plan (if no standard plan)")
    custom_duration_days = models.PositiveIntegerField(null=True, blank=True, help_text="Duration in days for custom plan")
    custom_price         = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date           = models.DateField(default=date.today)
    end_date             = models.DateField(null=True, blank=True)
    amount_paid          = models.DecimalField(max_digits=10, decimal_places=2)
    status               = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    uses_cardio_equipment= models.BooleanField(default=False, verbose_name="Uses Cardio/Electronic Equipment")
    uses_free_weights    = models.BooleanField(default=True,  verbose_name="Uses Free Weights Area")
    has_personal_trainer = models.BooleanField(default=False, verbose_name="Has Personal Trainer")
    trainer              = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='trained_memberships', limit_choices_to={'role':'trainer'})
    trainer_sessions_per_month = models.PositiveSmallIntegerField(default=0)
    has_locker           = models.BooleanField(default=False, verbose_name="Locker Included")
    has_steam_room       = models.BooleanField(default=False, verbose_name="Steam Room Access")
    notes                = models.TextField(blank=True)
    freeze_start         = models.DateField(null=True, blank=True)
    freeze_days          = models.PositiveSmallIntegerField(default=0)
    created_at           = models.DateTimeField(auto_now_add=True)
    created_by           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_memberships')

    class Meta:
        ordering = ['-start_date']

    def save(self, *args, **kwargs):
        if not self.end_date:
            if self.plan and self.plan.duration > 0:
                self.end_date = self.start_date + relativedelta(months=self.plan.duration)
            elif self.custom_duration_days:
                self.end_date = self.start_date + timedelta(days=self.custom_duration_days)
            elif self.plan and self.plan.duration == 0 and self.plan.custom_days:
                self.end_date = self.start_date + timedelta(days=self.plan.custom_days)
            else:
                self.end_date = self.start_date + timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.member.full_name} — {self.plan_display_name}"

    @property
    def plan_display_name(self):
        return self.custom_plan_name or (self.plan.name if self.plan else "Custom Plan")

    @property
    def is_active(self):
        return self.status == 'active' and self.end_date and self.end_date >= date.today()

    @property
    def days_remaining(self):
        return max(0, (self.end_date - date.today()).days) if self.end_date else 0

    @property
    def total_plan_price(self):
        if self.custom_price is not None:
            return self.custom_price
        return self.plan.price if self.plan else 0


# ═══════════════════════════════════════════════════════════════
#  MEMBER ADD-ONS
# ═══════════════════════════════════════════════════════════════
class MemberAddOn(TenantModel):
    STATUS_CHOICES = [('active','Active'),('paused','Paused'),('cancelled','Cancelled'),('expired','Expired')]
    member     = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='addons')
    addon      = models.ForeignKey(AddOn, on_delete=models.SET_NULL, related_name='member_addons', null=True)
    start_date = models.DateField(default=date.today)
    end_date   = models.DateField(null=True, blank=True)
    quantity   = models.PositiveSmallIntegerField(default=1, help_text="e.g. number of sessions per month")
    rate       = models.DecimalField(max_digits=8, decimal_places=2, help_text="Actual charged rate")
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    notes      = models.CharField(max_length=200, blank=True)
    added_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.member.full_name} — {self.addon.name if self.addon else 'Add-on'}"

    @property
    def monthly_charge(self):
        return self.rate * self.quantity if self.addon and self.addon.billing_cycle in ('monthly','session') else self.rate


# ═══════════════════════════════════════════════════════════════
#  ATTENDANCE LOG
# ═══════════════════════════════════════════════════════════════
class AttendanceLog(TenantModel):
    CHECK_IN_METHOD = [('manual','Manual (Staff)'),('selfie','Selfie Check-in'),('card','ID Card')]
    member         = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendance')
    date           = models.DateField(default=date.today)
    is_present     = models.BooleanField(default=True)
    check_in_time  = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    method         = models.CharField(max_length=8, choices=CHECK_IN_METHOD, default='manual')
    marked_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_marks')
    notes          = models.CharField(max_length=200, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('member','date')
        ordering = ['-date','member__full_name']
        indexes = [models.Index(fields=['gym','date'])]

    def __str__(self):
        return f"{self.member.full_name} — {self.date}"


# ═══════════════════════════════════════════════════════════════
#  PAYMENT
# ═══════════════════════════════════════════════════════════════
class Payment(TenantModel):
    METHOD_CHOICES = [('cash','Cash'),('easypaisa','EasyPaisa'),('jazzcash','JazzCash'),('bank','Bank Transfer'),('other','Other')]
    STATUS_CHOICES = [('paid','Paid (Full)'),('partial','Partial Payment'),('pending','Pending'),('overdue','Overdue'),('waived','Waived')]
    PAYMENT_FOR    = [('membership','Membership Fee'),('addon','Add-On Service'),('locker','Locker Rent'),('trainer','Personal Trainer'),('deposit','Security Deposit'),('other','Other')]
    member            = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='payments')
    membership_record = models.ForeignKey(MembershipRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    payment_for       = models.CharField(max_length=12, choices=PAYMENT_FOR, default='membership')
    amount_due        = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_date      = models.DateField(default=date.today)
    due_date          = models.DateField()
    method            = models.CharField(max_length=12, choices=METHOD_CHOICES, default='cash')
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    transaction_id    = models.CharField(max_length=60, blank=True, help_text="EasyPaisa/JazzCash TID or bank ref no.")
    received_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='collected_payments')
    notes             = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']
        indexes = [models.Index(fields=['gym','status']), models.Index(fields=['gym','due_date'])]

    def __str__(self):
        return f"{self.member.full_name} Rs.{self.amount_paid}/{self.amount_due}"

    @property
    def balance_due(self):
        return self.amount_due - self.amount_paid

    def save(self, *args, **kwargs):
        if self.amount_paid >= self.amount_due:
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.status = 'partial'
        elif date.today() > self.due_date and self.amount_paid == 0:
            self.status = 'overdue'
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════
#  EXPENSE
# ═══════════════════════════════════════════════════════════════
class Expense(TenantModel):
    CATEGORY_CHOICES = [
        ('rent','Rent'),('electricity','Electricity / WAPDA'),('generator','Generator / Fuel'),
        ('trainer','Trainer Salary'),('staff','Other Staff Salary'),('supplements','Supplements / Retail Stock'),
        ('maintenance','Equipment Maintenance'),('purchase','Equipment Purchase'),('internet','Internet / WiFi'),
        ('water','Water Bills'),('cleaning','Cleaning / Hygiene'),('marketing','Marketing / Printing'),
        ('insurance','Insurance'),('tax','Tax / Government Fees'),('miscellaneous','Miscellaneous'),
    ]
    METHOD_CHOICES = [('cash','Cash'),('easypaisa','EasyPaisa'),('jazzcash','JazzCash'),('bank','Bank Transfer'),('other','Other')]
    category     = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title        = models.CharField(max_length=200)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField(default=date.today)
    method       = models.CharField(max_length=12, choices=METHOD_CHOICES, default='cash')
    vendor       = models.CharField(max_length=100, blank=True)
    receipt_no   = models.CharField(max_length=60, blank=True)
    description  = models.TextField(blank=True)
    employee     = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='related_expenses')
    logged_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logged_expenses')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-expense_date']
        indexes = [models.Index(fields=['gym','expense_date']), models.Index(fields=['gym','category'])]

    def __str__(self):
        return f"{self.get_category_display()} — {self.title}"


# ═══════════════════════════════════════════════════════════════
#  WHATSAPP TEMPLATES
# ═══════════════════════════════════════════════════════════════
class WhatsAppTemplate(TenantModel):
    TEMPLATE_TYPE = [('fee_reminder','Fee Reminder'),('welcome','Welcome Message'),
                     ('expiry_warning','Expiry Warning (7 days)'),('birthday','Birthday Wish'),('custom','Custom')]
    name          = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPE, default='fee_reminder')
    body          = models.TextField(help_text="Placeholders: {member_name} {amount_due} {due_date} {gym_name} {gym_phone} {expiry_date} {plan_name}")
    is_default    = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default','name']

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

    def render(self, member, amount_due=None, due_date=None, gym=None, expiry_date=None, plan_name=None):
        sym = gym.currency_symbol if gym else "Rs."
        ctx = {
            'member_name': member.full_name, 'phone': member.phone,
            'amount_due': f"{sym}{amount_due}" if amount_due else "your outstanding fee",
            'due_date': str(due_date) if due_date else "soon",
            'expiry_date': str(expiry_date) if expiry_date else "soon",
            'plan_name': plan_name or "your membership",
            'gym_name': gym.name if gym else "our gym",
            'gym_phone': (gym.whatsapp or gym.phone) if gym else "",
        }
        text = self.body
        for k,v in ctx.items():
            text = text.replace('{'+k+'}', str(v))
        return text
