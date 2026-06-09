"""GYMKHANA — Views (Multi-Tenant)
Every query is scoped to request.user's gym via get_gym(request).
Two gym owners can NEVER see each other's data.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import JsonResponse, Http404
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator
from django.urls import reverse
from datetime import date, timedelta
import json

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

from .models import (
    Gym, UserProfile, Member, MembershipPlan, MembershipRecord,
    AddOn, MemberAddOn, Locker, LockerAssignment,
    Employee, EmployeeAttendance, EmployeeSalaryPayment,
    AttendanceLog, Payment, Expense, WhatsAppTemplate
)
from .forms import (
    GymForm, MembershipPlanForm, AddOnForm, MemberForm, MembershipRecordForm,
    MemberAddOnForm, LockerForm, LockerAssignmentForm, EmployeeForm,
    EmployeeSalaryForm, PaymentForm, ExpenseForm, WhatsAppTemplateForm
)


# ─────────────────────────────────────────────
# TENANT HELPERS
# ─────────────────────────────────────────────
def get_gym(request):
    """Return the Gym (tenant) for the logged-in user. Raises 404 if none.
    Cached on the request object so repeated calls in one request hit the DB once."""
    cached = getattr(request, '_gym_cache', None)
    if cached is not None:
        return cached
    try:
        profile = UserProfile.objects.select_related('gym').get(user=request.user)
        gym = profile.gym
    except UserProfile.DoesNotExist:
        gym = Gym.objects.filter(owner=request.user).first()
        if gym:
            UserProfile.objects.get_or_create(user=request.user, defaults={'gym': gym, 'is_owner': True})
        else:
            raise Http404("No gym associated with this account.")
    request._gym_cache = gym
    return gym


def t404(qs_model, gym, **kwargs):
    """get_object_or_404 but always scoped to gym."""
    return get_object_or_404(qs_model, gym=gym, **kwargs)


def is_owner_mode(request):
    """True when the session has been elevated to Owner mode via the 4-digit key,
    or the logged-in user is the registered gym owner who has elevated."""
    return bool(request.session.get('owner_mode'))


def owner_required(view):
    """Gate a view so only Owner mode can access it (reports, financials, settings)."""
    from functools import wraps
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not is_owner_mode(request):
            messages.warning(request, 'Owner mode required. Enter your 4-digit owner key to continue.')
            return redirect(f"{reverse('elevate')}?next={request.path}")
        return view(request, *args, **kwargs)
    return _wrapped


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        u = authenticate(request, username=request.POST.get('username','').strip(),
                         password=request.POST.get('password',''))
        if u:
            login(request, u)
            return redirect(request.GET.get('next','dashboard'))
        messages.error(request, 'Invalid username or password.')
    return render(request, 'gym/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def elevate(request):
    """Switch from Employee mode to Owner mode using the gym's 4-digit key."""
    gym = get_gym(request)
    nxt = request.GET.get('next') or request.POST.get('next') or reverse('dashboard')
    if request.method == 'POST':
        key = request.POST.get('owner_key', '').strip()
        if key == (gym.owner_key or '0000'):
            request.session['owner_mode'] = True
            messages.success(request, 'Owner mode unlocked.')
            return redirect(nxt)
        messages.error(request, 'Incorrect owner key.')
    return render(request, 'gym/elevate.html', {'next': nxt})


@login_required
def lock_owner(request):
    """Drop back to Employee mode."""
    request.session['owner_mode'] = False
    messages.success(request, 'Switched to Employee mode.')
    return redirect('dashboard')


def register_view(request):
    """Sign up a NEW gym owner. Each signup creates an isolated gym tenant."""
    if request.method == 'POST':
        un = request.POST.get('username','').strip()
        em = request.POST.get('email','').strip()
        gym_name = request.POST.get('gym_name','').strip() or "My Gym"
        owner_key = request.POST.get('owner_key','').strip()
        p1 = request.POST.get('password1','')
        p2 = request.POST.get('password2','')
        if not un or not p1:
            messages.error(request, 'Username and password are required.')
        elif p1 != p2:
            messages.error(request, 'Passwords do not match.')
        elif len(p1) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
        elif not (owner_key.isdigit() and len(owner_key) == 4):
            messages.error(request, 'Owner key must be exactly 4 digits.')
        elif User.objects.filter(username=un).exists():
            messages.error(request, 'Username already taken.')
        else:
            user = User.objects.create_user(username=un, email=em, password=p1)
            user.is_staff = True  # allow django admin access for own data
            user.save()
            gym = Gym.objects.create(name=gym_name, owner=user, email=em,
                        owner_key=owner_key, subscription_status='trial',
                        subscription_until=date.today()+timedelta(days=30))
            UserProfile.objects.create(user=user, gym=gym, is_owner=True, role='owner')
            _seed_defaults(gym)
            login(request, user)
            request.session['owner_mode'] = True  # creator starts in owner mode
            messages.success(request, f'Welcome! "{gym_name}" is ready (30-day trial). Set up your details below.')
            return redirect('gym_settings')
    return render(request, 'gym/register.html')


def _seed_defaults(gym):
    """Create starter plans + WhatsApp templates for a brand-new gym."""
    plans = [
        ("Monthly", 1, 3000, True, True, False, False, False),
        ("3-Month", 3, 8000, True, True, False, False, False),
        ("6-Month", 6, 15000, True, True, True, True, False),
        ("Annual", 12, 28000, True, True, True, True, True),
    ]
    for name, dur, price, cardio, weights, trainer, locker, steam in plans:
        MembershipPlan.objects.create(
            gym=gym, name=name, duration=dur, price=price,
            includes_cardio=cardio, includes_weights=weights,
            includes_trainer=trainer, includes_locker=locker, includes_steam=steam
        )
    addons = [
        ("Personal Trainer (Monthly)", 'trainer', 5000, 'monthly'),
        ("Cardio / Treadmill Access", 'cardio', 1000, 'monthly'),
        ("Locker Rental", 'locker', 500, 'monthly'),
        ("Steam Room", 'steam', 1500, 'monthly'),
    ]
    for name, atype, price, cycle in addons:
        AddOn.objects.create(gym=gym, name=name, addon_type=atype, price=price, billing_cycle=cycle)
    templates = [
        ('Fee Reminder', 'fee_reminder',
         'Assalam o Alaikum {member_name}! \U0001F64F\n\nYour gym fee of *{amount_due}* is due on *{due_date}*. Kindly clear it at your earliest.\n\nShukria,\n{gym_name}\n\U0001F4DE {gym_phone}', True),
        ('Expiry Warning', 'expiry_warning',
         'Dear {member_name},\n\nYour *{plan_name}* expires on *{expiry_date}*. Renew now to keep your spot! \U0001F4AA\n\n{gym_name}', False),
        ('Welcome Message', 'welcome',
         'Welcome to {gym_name}, {member_name}! \U0001F389\n\nWe are excited to have you. Let the gains begin! \U0001F3CB\n\n\U0001F4DE {gym_phone}', False),
    ]
    for name, ttype, body, is_def in templates:
        WhatsAppTemplate.objects.create(gym=gym, name=name, template_type=ttype, body=body, is_default=is_def)


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@login_required
def dashboard(request):
    gym   = get_gym(request)
    today = date.today()
    week_ago = today - timedelta(days=7)

    # Analytics period: custom range if provided, else current month.
    start_str = request.GET.get('start',''); end_str = request.GET.get('end','')
    custom_range = False; period_start = today.replace(day=1); period_end = today
    if start_str and end_str:
        try:
            from datetime import datetime as _dt
            period_start = _dt.strptime(start_str, '%Y-%m-%d').date()
            period_end   = _dt.strptime(end_str, '%Y-%m-%d').date()
            if period_end < period_start:
                period_start, period_end = period_end, period_start
            custom_range = True
        except ValueError:
            period_start = today.replace(day=1); period_end = today
    rev_filter = {'payment_date__range': [period_start, period_end]}
    exp_filter = {'expense_date__range': [period_start, period_end]}

    total_members   = Member.objects.filter(gym=gym, status='active').count()
    today_present   = AttendanceLog.objects.filter(gym=gym, date=today, is_present=True).count()
    monthly_revenue = Payment.objects.filter(gym=gym, status__in=['paid','partial'], **rev_filter).aggregate(t=Sum('amount_paid'))['t'] or 0
    monthly_expenses= Expense.objects.filter(gym=gym, **exp_filter).aggregate(t=Sum('amount'))['t'] or 0
    net_profit      = monthly_revenue - monthly_expenses
    overdue_count   = Payment.objects.filter(gym=gym, status='overdue').values('member').distinct().count()
    outstanding     = (Payment.objects.filter(gym=gym, status__in=['overdue','partial','pending'])
                        .aggregate(d=Sum('amount_due'), p=Sum('amount_paid')))
    total_outstanding = (outstanding['d'] or 0) - (outstanding['p'] or 0)
    new_this_month  = Member.objects.filter(gym=gym, join_date__range=[period_start, period_end]).count()
    checkins_week   = AttendanceLog.objects.filter(gym=gym, date__gte=week_ago, is_present=True).count()

    expiring_soon = MembershipRecord.objects.filter(gym=gym, status='active', end_date__gte=today, end_date__lte=today+timedelta(days=7)).select_related('member','plan').order_by('end_date')[:8]
    recent_checkins = AttendanceLog.objects.filter(gym=gym, date=today, is_present=True).select_related('member').order_by('-created_at')[:12]
    recent_payments = Payment.objects.filter(gym=gym, status__in=['paid','partial']).select_related('member').order_by('-payment_date','-created_at')[:10]

    total_employees  = Employee.objects.filter(gym=gym, status='active').count()
    occupied_lockers = Locker.objects.filter(gym=gym, status='occupied').count()
    total_lockers    = Locker.objects.filter(gym=gym).count()

    return render(request, 'gym/dashboard.html', {
        'custom_range': custom_range,
        'period_start': period_start.isoformat(), 'period_end': period_end.isoformat(),
        'gym': gym, 'total_members': total_members, 'today_present': today_present,
        'monthly_revenue': monthly_revenue, 'monthly_expenses': monthly_expenses,
        'net_profit': net_profit, 'overdue_count': overdue_count,
        'total_outstanding': total_outstanding, 'new_this_month': new_this_month,
        'checkins_week': checkins_week,
        'expiring_soon': expiring_soon, 'recent_checkins': recent_checkins,
        'recent_payments': recent_payments, 'total_employees': total_employees,
        'occupied_lockers': occupied_lockers, 'total_lockers': total_lockers, 'today': today,
    })


# ─────────────────────────────────────────────
# MEMBERS
# ─────────────────────────────────────────────
@login_required
def member_list(request):
    gym = get_gym(request)
    qs = (Member.objects.filter(gym=gym)
          .select_related('assigned_trainer')
          .prefetch_related('memberships__plan')
          .order_by('-join_date'))
    q = request.GET.get('q','').strip(); shift = request.GET.get('shift',''); status = request.GET.get('status',''); trainer = request.GET.get('trainer','')
    if q: qs = qs.filter(Q(full_name__icontains=q)|Q(phone__icontains=q)|Q(cnic__icontains=q))
    if shift: qs = qs.filter(shift=shift)
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status='left')  # hide former members from the active roster
    if trainer: qs = qs.filter(assigned_trainer_id=trainer)
    total = qs.count()
    page_obj = Paginator(qs, 30).get_page(request.GET.get('page'))
    # Attach active membership in Python from prefetched data (avoids N+1 queries)
    today = date.today()
    for m in page_obj:
        active = None
        for ms in sorted(m.memberships.all(), key=lambda x: x.start_date, reverse=True):
            if ms.status == 'active' and ms.end_date and ms.end_date >= today:
                active = ms; break
        m.active_mem = active
    trainers = Employee.objects.filter(gym=gym, role='trainer', status='active')
    former_count = Member.objects.filter(gym=gym, status='left').count()
    return render(request,'gym/member_list.html',{'page_obj':page_obj,'q':q,'shift':shift,'status':status,'trainer':trainer,'trainers':trainers,'total':total,'former_count':former_count})

@login_required
def former_members(request):
    """Archive of members who have left the gym (records are retained, never lost)."""
    gym = get_gym(request)
    qs = Member.objects.filter(gym=gym, status='left').order_by('-left_date','full_name')
    q = request.GET.get('q','').strip()
    if q: qs = qs.filter(Q(full_name__icontains=q)|Q(phone__icontains=q)|Q(cnic__icontains=q))
    page_obj = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request,'gym/former_members.html',{'page_obj':page_obj,'q':q,'total':qs.count()})

@login_required
def member_print(request, pk):
    """Printable member record card."""
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    active_mem = member.active_membership
    return render(request,'gym/member_print.html',{'member':member,'gym':gym,'active_mem':active_mem,'today':date.today()})

@login_required
def member_add(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = MemberForm(request.POST, request.FILES, gym=gym)
        if form.is_valid():
            try:
                m = form.save(commit=False); m.gym = gym; m.registered_by = request.user; m.save()
            except IntegrityError:
                messages.error(request, 'A member with this phone number already exists in your gym.')
                return render(request,'gym/member_form.html',{'form':form,'action':'Add New'})
            messages.success(request, f'Member "{m.full_name}" registered.')
            return redirect('member_detail', pk=m.pk)
    else:
        form = MemberForm(gym=gym)
    return render(request,'gym/member_form.html',{'form':form,'action':'Add New'})

@login_required
def member_edit(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    if request.method == 'POST':
        form = MemberForm(request.POST, request.FILES, instance=member, gym=gym)
        if form.is_valid():
            try:
                m = form.save()
            except IntegrityError:
                messages.error(request, 'Could not save: that phone number is already in use.')
                return render(request,'gym/member_form.html',{'form':form,'action':'Edit','member':member})
            if m.status == 'left':
                la = m.active_locker
                if la:
                    la.is_active = False; la.released_date = date.today(); la.save()
            messages.success(request,'Member updated.')
            return redirect('member_detail', pk=member.pk)
    else:
        form = MemberForm(instance=member, gym=gym)
    return render(request,'gym/member_form.html',{'form':form,'action':'Edit','member':member})

@login_required
def member_detail(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    memberships = member.memberships.select_related('plan','trainer').order_by('-start_date')
    payments    = member.payments.order_by('-payment_date')[:15]
    attendance  = member.attendance.order_by('-date')[:31]
    present_days= member.attendance.filter(is_present=True).count()
    addons      = member.addons.select_related('addon').filter(status='active')
    active_locker = member.active_locker
    active_mem  = member.active_membership
    agg = member.payments.filter(status__in=['overdue','partial','pending']).aggregate(d=Sum('amount_due'), p=Sum('amount_paid'))
    outstanding = (agg['d'] or 0) - (agg['p'] or 0)
    return render(request,'gym/member_detail.html',{'member':member,'memberships':memberships,'payments':payments,'attendance':attendance,'present_days':present_days,'addons':addons,'active_locker':active_locker,'active_mem':active_mem,'outstanding':outstanding,'today':date.today()})

@login_required
def member_delete(request, pk):
    """Archive a member as 'left' (data retained). Permanent delete is owner-only."""
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action','archive')
        if action == 'hard_delete' and is_owner_mode(request):
            name = member.full_name; member.delete()
            messages.success(request, f'Member "{name}" permanently deleted.')
            return redirect('member_list')
        member.status = 'left'
        member.left_date = date.today()
        member.left_reason = request.POST.get('left_reason','').strip()
        member.save(update_fields=['status','left_date','left_reason'])
        # free any locker held by this member
        la = member.active_locker
        if la:
            la.is_active = False; la.released_date = date.today(); la.save()
        messages.success(request, f'"{member.full_name}" moved to former members. Their record is retained.')
        return redirect('member_list')
    return render(request,'gym/confirm_delete.html',{'object':member,'type':'Member','can_hard_delete':is_owner_mode(request)})

@login_required
def member_restore(request, pk):
    """Bring a former member back to active roster."""
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    member.status = 'active'; member.left_date = None; member.left_reason = ''
    member.save(update_fields=['status','left_date','left_reason'])
    messages.success(request, f'"{member.full_name}" restored to active members.')
    return redirect('member_detail', pk=member.pk)

@login_required
def assign_membership(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    plans = MembershipPlan.objects.filter(gym=gym, is_active=True)
    trainers = Employee.objects.filter(gym=gym, role='trainer', status='active')
    if request.method == 'POST':
        form = MembershipRecordForm(request.POST, gym=gym)
        if form.is_valid():
            try:
                with transaction.atomic():
                    rec = form.save(commit=False); rec.gym = gym; rec.member = member; rec.created_by = request.user; rec.save()
                    plan_price = rec.custom_price or (rec.plan.price if rec.plan else rec.amount_paid)
                    Payment.objects.create(gym=gym, member=member, membership_record=rec, payment_for='membership',
                        amount_due=plan_price, amount_paid=rec.amount_paid, payment_date=rec.start_date,
                        due_date=rec.start_date, method=request.POST.get('payment_method','cash'), received_by=request.user)
                    if member.status == 'left':
                        member.left_date = None; member.left_reason = ''
                    member.status = 'active'; member.save(update_fields=['status','left_date','left_reason'])
            except IntegrityError:
                messages.error(request, 'Could not assign the plan. Please review the details and try again.')
                return render(request,'gym/assign_membership.html',{'form':form,'member':member,'plans':plans,'trainers':trainers})
            messages.success(request, f'Plan assigned: {rec.plan_display_name}')
            return redirect('member_detail', pk=member.pk)
    else:
        form = MembershipRecordForm(initial={'start_date':date.today()}, gym=gym)
    return render(request,'gym/assign_membership.html',{'form':form,'member':member,'plans':plans,'trainers':trainers})

@login_required
def assign_addon(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    addons = AddOn.objects.filter(gym=gym, is_active=True)
    if request.method == 'POST':
        form = MemberAddOnForm(request.POST, gym=gym)
        if form.is_valid():
            ao = form.save(commit=False); ao.gym = gym; ao.member = member; ao.added_by = request.user; ao.save()
            Payment.objects.create(gym=gym, member=member, payment_for='addon',
                amount_due=ao.monthly_charge, amount_paid=ao.monthly_charge if request.POST.get('paid_now') else 0,
                payment_date=ao.start_date, due_date=ao.start_date, method=request.POST.get('payment_method','cash'),
                received_by=request.user, notes=f"Add-on: {ao.addon.name}")
            messages.success(request, f'Add-on "{ao.addon.name}" assigned.')
            return redirect('member_detail', pk=member.pk)
    else:
        form = MemberAddOnForm(initial={'start_date':date.today(),'rate':0}, gym=gym)
    return render(request,'gym/assign_addon.html',{'form':form,'member':member,'addons':addons})

@login_required
def assign_locker(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    if member.active_locker:
        messages.warning(request, 'Member already has an active locker.')
        return redirect('member_detail', pk=member.pk)
    zone = 'ladies' if member.shift == 'ladies' else 'gents'
    lockers = Locker.objects.filter(gym=gym, status='available')
    if request.method == 'POST':
        form = LockerAssignmentForm(request.POST, gym=gym)
        if form.is_valid():
            la = form.save(commit=False)
            rate = la.monthly_rate or 0
            # PAYMENT GATE: the locker fee must be paid before the locker is assigned.
            if rate > 0 and (la.amount_paid or 0) < rate:
                messages.error(request,
                    f'Locker not assigned. The locker fee of Rs.{rate:.0f} must be paid in full first '
                    f'(received Rs.{(la.amount_paid or 0):.0f}).')
                return render(request,'gym/assign_locker.html',
                    {'form':form,'member':member,'lockers':lockers,'zone':zone})
            la.gym = gym; la.assigned_by = request.user; la.is_active = True; la.save()
            # Record the locker-fee payment
            if (la.amount_paid or 0) > 0:
                Payment.objects.create(gym=gym, member=member, payment_for='locker',
                    amount_due=rate or la.amount_paid, amount_paid=la.amount_paid,
                    payment_date=la.assigned_date, due_date=la.assigned_date,
                    method=request.POST.get('payment_method','cash'), received_by=request.user,
                    notes=f"Locker {la.locker.locker_number} fee")
            # Record the deposit (if any) as its own payment
            if la.deposit_paid > 0:
                Payment.objects.create(gym=gym, member=member, payment_for='deposit',
                    amount_due=la.deposit_paid, amount_paid=la.deposit_paid, payment_date=la.assigned_date,
                    due_date=la.assigned_date, method=request.POST.get('payment_method','cash'),
                    received_by=request.user, notes=f"Locker {la.locker.locker_number} deposit")
            messages.success(request, f'Locker {la.locker.locker_number} assigned (fee paid: Rs.{(la.amount_paid or 0):.0f}).')
            return redirect('member_detail', pk=member.pk)
    else:
        first_avail = Locker.objects.filter(gym=gym, status='available', zone=zone).first()
        rate = first_avail.monthly_rate if first_avail else 0
        form = LockerAssignmentForm(initial={'member':member,'assigned_date':date.today(),
            'monthly_rate': rate, 'amount_paid': rate}, gym=gym)
    return render(request,'gym/assign_locker.html',{'form':form,'member':member,'lockers':lockers,'zone':zone})

@login_required
def release_locker(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    if request.method == 'POST':
        # Deactivate EVERY active locker assignment this member holds, and free each locker.
        active = LockerAssignment.objects.filter(gym=gym, member=member, is_active=True)
        freed = []
        for la in active:
            la.is_active = False
            la.released_date = date.today()
            la.save(update_fields=['is_active', 'released_date'])
            lk = la.locker
            if not lk.assignments.filter(is_active=True).exists():
                lk.status = 'available'
                lk.save(update_fields=['status'])
                freed.append(lk.locker_number)
        if freed:
            messages.success(request, f"Locker {', '.join(freed)} released and now available.")
        else:
            messages.info(request, 'No active locker to release.')
    return redirect('member_detail', pk=member.pk)


# ─────────────────────────────────────────────
# ATTENDANCE (MEMBERS)
# ─────────────────────────────────────────────
@login_required
def attendance_today(request):
    gym = get_gym(request); today = date.today()
    q = request.GET.get('q','').strip(); shift = request.GET.get('shift','')
    qs = Member.objects.filter(gym=gym, status='active').order_by('full_name')
    if q: qs = qs.filter(Q(full_name__icontains=q)|Q(phone__icontains=q))
    if shift: qs = qs.filter(shift=shift)
    log_map = {l.member_id:l for l in AttendanceLog.objects.filter(gym=gym, date=today).select_related('member')}
    data = [{'member':m,'log':log_map.get(m.id),'present':log_map[m.id].is_present if m.id in log_map else None} for m in qs]
    return render(request,'gym/attendance_today.html',{'members_data':data,'today':today,'q':q,'shift':shift,
        'present_count':sum(1 for x in data if x['present'] is True),
        'absent_count':sum(1 for x in data if x['present'] is False),
        'unmarked_count':sum(1 for x in data if x['present'] is None)})

@login_required
def mark_attendance(request):
    gym = get_gym(request)
    if request.method == 'POST':
        data = json.loads(request.body)
        member = t404(Member, gym, pk=data.get('member_id'))
        is_present = data.get('is_present', True); today = date.today()
        log, created = AttendanceLog.objects.get_or_create(gym=gym, member=member, date=today, defaults={
            'is_present':is_present,'check_in_time':timezone.localtime().time() if is_present else None,'marked_by':request.user})
        if not created:
            log.is_present = is_present
            if is_present and not log.check_in_time: log.check_in_time = timezone.localtime().time()
            log.marked_by = request.user; log.save()
        return JsonResponse({'success':True,'member_name':member.full_name,'is_present':log.is_present,
            'check_in_time':str(log.check_in_time)[:5] if log.check_in_time else None})
    return JsonResponse({'success':False}, status=400)

@login_required
def attendance_history(request, pk):
    gym = get_gym(request); member = t404(Member, gym, pk=pk)
    end = date.today(); start = end - timedelta(days=89)
    logs = member.attendance.filter(date__range=[start,end]).order_by('-date')
    return render(request,'gym/attendance_history.html',{'member':member,'logs':logs,
        'total_present':logs.filter(is_present=True).count(),'total_absent':logs.filter(is_present=False).count(),
        'start_date':start,'end_date':end})


# ─────────────────────────────────────────────
# PAYMENTS
# ─────────────────────────────────────────────
@login_required
def payment_list(request):
    gym = get_gym(request)
    qs = Payment.objects.filter(gym=gym).select_related('member').order_by('-payment_date')
    q = request.GET.get('q','').strip(); status = request.GET.get('status',''); method = request.GET.get('method',''); month = request.GET.get('month',''); pfor = request.GET.get('pfor','')
    if q: qs = qs.filter(Q(member__full_name__icontains=q)|Q(member__phone__icontains=q)|Q(transaction_id__icontains=q))
    if status: qs = qs.filter(status=status)
    if method: qs = qs.filter(method=method)
    if pfor: qs = qs.filter(payment_for=pfor)
    if month:
        try:
            yr,mo = map(int, month.split('-')); qs = qs.filter(payment_date__year=yr, payment_date__month=mo)
        except: pass
    total_collected = qs.filter(status__in=['paid','partial']).aggregate(t=Sum('amount_paid'))['t'] or 0
    page_obj = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request,'gym/payment_list.html',{'page_obj':page_obj,'q':q,'status':status,'method':method,'month':month,'pfor':pfor,'total_collected':total_collected})

@login_required
def payment_add(request, member_pk=None):
    gym = get_gym(request)
    member = t404(Member, gym, pk=member_pk) if member_pk else None
    # Outstanding balance for this member (sum of unpaid dues across all payments)
    outstanding = 0; pending_rows = []
    if member:
        agg = member.payments.filter(status__in=['overdue','partial','pending']).aggregate(
            d=Sum('amount_due'), p=Sum('amount_paid'))
        outstanding = (agg['d'] or 0) - (agg['p'] or 0)
        pending_rows = member.payments.filter(status__in=['overdue','partial','pending']).order_by('payment_date')
    if request.method == 'POST':
        form = PaymentForm(request.POST, gym=gym)
        if form.is_valid():
            try:
                p = form.save(commit=False); p.gym = gym; p.received_by = request.user; p.save()
            except IntegrityError:
                messages.error(request, 'Could not save this payment. Please check the details and try again.')
                return render(request,'gym/payment_form.html',{'form':form,'member':member,'outstanding':outstanding,'pending_rows':pending_rows})
            messages.success(request, 'Payment recorded.')
            return redirect('member_detail', pk=p.member.pk) if member_pk else redirect('payment_list')
    else:
        initial = {'payment_date':date.today(),'due_date':date.today()}
        if member:
            initial['member'] = member
            if outstanding > 0:
                initial['amount_due'] = outstanding   # prefill what they still owe
                initial['amount_paid'] = outstanding
        form = PaymentForm(initial=initial, gym=gym)
    return render(request,'gym/payment_form.html',{'form':form,'member':member,'outstanding':outstanding,'pending_rows':pending_rows})

@login_required
def defaulter_list(request):
    gym = get_gym(request)
    defaulters = (Payment.objects.filter(gym=gym, status__in=['overdue','partial','pending'])
        .values('member__id','member__full_name','member__phone','member__shift','member__cnic')
        .annotate(total_due=Sum('amount_due'),total_paid=Sum('amount_paid'),balance=Sum('amount_due')-Sum('amount_paid'),records=Count('id'))
        .order_by('-balance'))
    total_outstanding = sum(d['balance'] for d in defaulters) or 0
    return render(request,'gym/defaulter_list.html',{'defaulters':defaulters,'total_outstanding':total_outstanding,'count':defaulters.count()})


# ─────────────────────────────────────────────
# EXPENSES
# ─────────────────────────────────────────────
@login_required
@owner_required
def expense_list(request):
    gym = get_gym(request)
    qs = Expense.objects.filter(gym=gym).order_by('-expense_date')
    category = request.GET.get('category',''); month = request.GET.get('month',''); q = request.GET.get('q','').strip()
    if category: qs = qs.filter(category=category)
    if month:
        try:
            yr,mo = map(int, month.split('-')); qs = qs.filter(expense_date__year=yr, expense_date__month=mo)
        except: pass
    if q: qs = qs.filter(Q(title__icontains=q)|Q(vendor__icontains=q))
    cat_totals = qs.values('category').annotate(total=Sum('amount')).order_by('-total')
    total = qs.aggregate(t=Sum('amount'))['t'] or 0
    page_obj = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request,'gym/expense_list.html',{'page_obj':page_obj,'category':category,'month':month,'q':q,'total':total,'cat_totals':cat_totals,'categories':Expense.CATEGORY_CHOICES})

@login_required
@owner_required
def expense_add(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, gym=gym)
        if form.is_valid():
            e = form.save(commit=False); e.gym = gym; e.logged_by = request.user; e.save()
            messages.success(request, f'Expense logged: Rs.{e.amount}')
            return redirect('expense_list')
    else:
        form = ExpenseForm(initial={'expense_date':date.today()}, gym=gym)
    return render(request,'gym/expense_form.html',{'form':form,'action':'Add'})

@login_required
@owner_required
def expense_edit(request, pk):
    gym = get_gym(request); exp = t404(Expense, gym, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=exp, gym=gym)
        if form.is_valid():
            form.save(); messages.success(request,'Expense updated.')
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=exp, gym=gym)
    return render(request,'gym/expense_form.html',{'form':form,'action':'Edit','expense':exp})

@login_required
@owner_required
def expense_delete(request, pk):
    gym = get_gym(request); exp = t404(Expense, gym, pk=pk)
    if request.method == 'POST':
        exp.delete(); messages.success(request,'Expense deleted.')
        return redirect('expense_list')
    return render(request,'gym/confirm_delete.html',{'object':exp,'type':'Expense'})


# ─────────────────────────────────────────────
# EMPLOYEES
# ─────────────────────────────────────────────
@login_required
def employee_list(request):
    gym = get_gym(request)
    qs = Employee.objects.filter(gym=gym).order_by('role','full_name')
    q = request.GET.get('q','').strip(); role = request.GET.get('role',''); status = request.GET.get('status','active')
    if q: qs = qs.filter(Q(full_name__icontains=q)|Q(phone__icontains=q)|Q(cnic__icontains=q))
    if role: qs = qs.filter(role=role)
    if status: qs = qs.filter(status=status)
    total_salary = qs.filter(status='active').aggregate(t=Sum('monthly_salary'))['t'] or 0
    return render(request,'gym/employee_list.html',{'employees':qs,'q':q,'role':role,'status':status,'total_salary':total_salary,'roles':Employee.ROLE_CHOICES})

@login_required
def employee_add(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, gym=gym)
        if form.is_valid():
            try:
                e = form.save(commit=False); e.gym = gym; e.save()
            except IntegrityError:
                messages.error(request, 'An employee with this phone number already exists.')
                return render(request,'gym/employee_form.html',{'form':form,'action':'Add'})
            messages.success(request, 'Employee added.')
            return redirect('employee_detail', pk=e.pk)
    else:
        form = EmployeeForm(initial={'join_date':date.today()}, gym=gym)
    return render(request,'gym/employee_form.html',{'form':form,'action':'Add'})

@login_required
def employee_edit(request, pk):
    gym = get_gym(request); emp = t404(Employee, gym, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=emp, gym=gym)
        if form.is_valid():
            form.save(); messages.success(request,'Employee updated.')
            return redirect('employee_detail', pk=emp.pk)
    else:
        form = EmployeeForm(instance=emp, gym=gym)
    return render(request,'gym/employee_form.html',{'form':form,'action':'Edit','employee':emp})

@login_required
def employee_detail(request, pk):
    gym = get_gym(request); emp = t404(Employee, gym, pk=pk)
    salary_history = emp.salary_payments.order_by('-paid_date')[:12]
    attendance_log = emp.attendance.order_by('-date')[:31]
    trainees = emp.trainees.filter(status='active') if emp.is_trainer else []
    total_paid = emp.salary_payments.aggregate(t=Sum('net_amount'))['t'] or 0
    return render(request,'gym/employee_detail.html',{'emp':emp,'salary_history':salary_history,'attendance_log':attendance_log,'trainees':trainees,'total_paid':total_paid})

@login_required
def employee_delete(request, pk):
    gym = get_gym(request); emp = t404(Employee, gym, pk=pk)
    if request.method == 'POST':
        name = emp.full_name; emp.delete()
        messages.success(request, f'Employee "{name}" removed.')
        return redirect('employee_list')
    return render(request,'gym/confirm_delete.html',{'object':emp,'type':'Employee'})

@login_required
@owner_required
def pay_salary(request, pk):
    gym = get_gym(request); emp = t404(Employee, gym, pk=pk)
    if request.method == 'POST':
        form = EmployeeSalaryForm(request.POST, gym=gym)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sp = form.save(commit=False); sp.gym = gym; sp.paid_by = request.user; sp.save()
                    Expense.objects.create(gym=gym, category='trainer' if emp.role=='trainer' else 'staff',
                        title=f"Salary - {emp.full_name} ({sp.month.strftime('%b %Y')})", amount=sp.net_amount,
                        expense_date=sp.paid_date, method=sp.method, employee=emp, logged_by=request.user)
            except IntegrityError:
                messages.error(request, f'A salary payment for {emp.full_name} in that month already exists.')
                return render(request,'gym/pay_salary.html',{'form':form,'emp':emp})
            messages.success(request, f'Salary {gym.currency_symbol}{sp.net_amount} paid to {emp.full_name}.')
            return redirect('employee_detail', pk=emp.pk)
    else:
        form = EmployeeSalaryForm(initial={'employee':emp,'month':date.today().replace(day=1),'amount':emp.monthly_salary,'paid_date':date.today()}, gym=gym)
    return render(request,'gym/pay_salary.html',{'form':form,'emp':emp})

@login_required
def employee_attendance(request):
    gym = get_gym(request); today = date.today()
    q = request.GET.get('q','').strip()
    qs = Employee.objects.filter(gym=gym, status='active').order_by('role','full_name')
    if q: qs = qs.filter(Q(full_name__icontains=q)|Q(phone__icontains=q))
    log_map = {l.employee_id:l for l in EmployeeAttendance.objects.filter(gym=gym, date=today)}
    data = [{'emp':e,'log':log_map.get(e.id),'present':log_map[e.id].is_present if e.id in log_map else None} for e in qs]
    return render(request,'gym/employee_attendance.html',{'data':data,'today':today,'q':q,
        'present':sum(1 for x in data if x['present'] is True),'absent':sum(1 for x in data if x['present'] is False)})

@login_required
def mark_employee_attendance(request):
    gym = get_gym(request)
    if request.method == 'POST':
        data = json.loads(request.body); emp = t404(Employee, gym, pk=data.get('emp_id')); today = date.today()
        log, created = EmployeeAttendance.objects.get_or_create(gym=gym, employee=emp, date=today, defaults={
            'is_present':data.get('is_present',True),'check_in_time':timezone.localtime().time(),'marked_by':request.user})
        if not created:
            log.is_present = data.get('is_present',True); log.marked_by = request.user; log.save()
        return JsonResponse({'success':True,'is_present':log.is_present})
    return JsonResponse({'success':False}, status=400)


# ─────────────────────────────────────────────
# LOCKERS
# ─────────────────────────────────────────────
@login_required
def locker_list(request):
    gym = get_gym(request)
    zone = request.GET.get('zone',''); status = request.GET.get('status','')
    qs = (Locker.objects.filter(gym=gym)
          .prefetch_related('assignments__member')
          .order_by('zone','locker_number'))
    if zone: qs = qs.filter(zone=zone)
    lockers = []
    available = occupied = maint = 0
    for lk in qs:
        active = next((a for a in lk.assignments.all() if a.is_active), None)
        if active:
            disp = 'occupied'; occupied += 1
        elif lk.status in ('maintenance','reserved'):
            disp = lk.status; maint += 1
        else:
            disp = 'available'; available += 1
        lk.disp = disp
        lk.occ = active.member if active else None
        if not status or status == disp:
            lockers.append(lk)
    return render(request,'gym/locker_list.html',{
        'lockers':lockers,'zone':zone,'status':status,
        'available':available,'occupied':occupied,'maint':maint})

@login_required
def locker_add(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = LockerForm(request.POST, gym=gym)
        if form.is_valid():
            try:
                l = form.save(commit=False); l.gym = gym; l.save()
            except IntegrityError:
                messages.error(request, 'A locker with this number already exists.')
                return render(request,'gym/locker_form.html',{'form':form,'action':'Add'})
            messages.success(request,'Locker added.')
            return redirect('locker_list')
    else:
        form = LockerForm(gym=gym)
    return render(request,'gym/locker_form.html',{'form':form,'action':'Add'})

@login_required
def locker_edit(request, pk):
    gym = get_gym(request); locker = t404(Locker, gym, pk=pk)
    if request.method == 'POST':
        form = LockerForm(request.POST, instance=locker, gym=gym)
        if form.is_valid():
            form.save(); messages.success(request,'Locker updated.')
            return redirect('locker_list')
    else:
        form = LockerForm(instance=locker, gym=gym)
    return render(request,'gym/locker_form.html',{'form':form,'action':'Edit','locker':locker})


# ─────────────────────────────────────────────
# PLANS & ADD-ONS
# ─────────────────────────────────────────────
@login_required
def plan_list(request):
    gym = get_gym(request)
    return render(request,'gym/plan_list.html',{'plans':MembershipPlan.objects.filter(gym=gym).order_by('duration','price')})

@login_required
def plan_add(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = MembershipPlanForm(request.POST)
        if form.is_valid():
            p = form.save(commit=False); p.gym = gym; p.save()
            messages.success(request,'Plan created.')
            return redirect('plan_list')
    else:
        form = MembershipPlanForm()
    return render(request,'gym/plan_form.html',{'form':form,'action':'Add'})

@login_required
def plan_edit(request, pk):
    gym = get_gym(request); plan = t404(MembershipPlan, gym, pk=pk)
    if request.method == 'POST':
        form = MembershipPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save(); messages.success(request,'Plan updated.')
            return redirect('plan_list')
    else:
        form = MembershipPlanForm(instance=plan)
    return render(request,'gym/plan_form.html',{'form':form,'action':'Edit','plan':plan})

@login_required
def addon_list(request):
    gym = get_gym(request)
    return render(request,'gym/addon_list.html',{'addons':AddOn.objects.filter(gym=gym).order_by('addon_type','name')})

@login_required
def addon_add(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = AddOnForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False); a.gym = gym; a.save()
            messages.success(request,'Add-on created.')
            return redirect('addon_list')
    else:
        form = AddOnForm()
    return render(request,'gym/addon_form.html',{'form':form,'action':'Add'})

@login_required
def addon_edit(request, pk):
    gym = get_gym(request); addon = t404(AddOn, gym, pk=pk)
    if request.method == 'POST':
        form = AddOnForm(request.POST, instance=addon)
        if form.is_valid():
            form.save(); messages.success(request,'Add-on updated.')
            return redirect('addon_list')
    else:
        form = AddOnForm(instance=addon)
    return render(request,'gym/addon_form.html',{'form':form,'action':'Edit','addon':addon})


@login_required
def plan_delete(request, pk):
    """Delete a plan. If it has membership history, archive (deactivate) it instead
    so historical records are preserved."""
    gym = get_gym(request); plan = t404(MembershipPlan, gym, pk=pk)
    if request.method == 'POST':
        in_use = MembershipRecord.objects.filter(gym=gym, plan=plan).exists()
        name = plan.name
        if in_use:
            plan.is_active = False; plan.save(update_fields=['is_active'])
            messages.success(request, f'Plan "{name}" has history, so it was archived (hidden from new sign-ups) to keep your records intact.')
        else:
            plan.delete()
            messages.success(request, f'Plan "{name}" deleted.')
        return redirect('plan_list')
    return render(request,'gym/confirm_delete.html',{'object':plan,'type':'Membership Plan'})


@login_required
def addon_delete(request, pk):
    gym = get_gym(request); addon = t404(AddOn, gym, pk=pk)
    if request.method == 'POST':
        in_use = MemberAddOn.objects.filter(gym=gym, addon=addon).exists()
        name = addon.name
        if in_use:
            addon.is_active = False; addon.save(update_fields=['is_active'])
            messages.success(request, f'Add-on "{name}" has history, so it was archived (hidden from new sign-ups) to keep your records intact.')
        else:
            addon.delete()
            messages.success(request, f'Add-on "{name}" deleted.')
        return redirect('addon_list')
    return render(request,'gym/confirm_delete.html',{'object':addon,'type':'Add-On'})


@login_required
def locker_delete(request, pk):
    gym = get_gym(request); locker = t404(Locker, gym, pk=pk)
    if request.method == 'POST':
        if locker.assignments.filter(is_active=True).exists():
            messages.error(request, 'This locker is currently occupied. Release it before deleting.')
            return redirect('locker_list')
        num = locker.locker_number
        locker.delete()
        messages.success(request, f'Locker {num} deleted.')
        return redirect('locker_list')
    return render(request,'gym/confirm_delete.html',{'object':locker,'type':'Locker'})


@login_required
def whatsapp_template_delete(request, pk):
    gym = get_gym(request); tpl = t404(WhatsAppTemplate, gym, pk=pk)
    if request.method == 'POST':
        name = tpl.name
        tpl.delete()
        messages.success(request, f'Template "{name}" deleted.')
        return redirect('whatsapp_templates')
    return render(request,'gym/confirm_delete.html',{'object':tpl,'type':'WhatsApp Template'})


# ─────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────
def _period(request):
    """Resolve reporting period from request: custom start/end or month selector."""
    from datetime import datetime as _dt
    today = date.today()
    start_str = request.GET.get('start',''); end_str = request.GET.get('end','')
    custom = False; p_start = p_end = None
    if start_str and end_str:
        try:
            p_start = _dt.strptime(start_str,'%Y-%m-%d').date()
            p_end   = _dt.strptime(end_str,'%Y-%m-%d').date()
            if p_end < p_start: p_start, p_end = p_end, p_start
            custom = True
        except ValueError:
            p_start = p_end = None
    if not custom:
        try:
            yr = int(request.GET.get('year', today.year)); mo = int(request.GET.get('month', today.month))
        except (ValueError, TypeError):
            yr, mo = today.year, today.month
        p_start = date(yr, mo, 1); p_end = p_start + relativedelta(months=1) - timedelta(days=1)
    else:
        yr, mo = p_start.year, p_start.month
    months = [{'year':(today-relativedelta(months=i)).year,'month':(today-relativedelta(months=i)).month,
               'label':(today-relativedelta(months=i)).strftime('%B %Y')} for i in range(12)]
    return p_start, p_end, custom, yr, mo, months


@login_required
@owner_required
def reports(request):
    """Lean main report: headline numbers, P&L, and the Excel-style ledger."""
    gym = get_gym(request)
    p_start, p_end, custom_range, yr, mo, months = _period(request)

    revenue_qs = Payment.objects.filter(gym=gym, payment_date__range=[p_start,p_end], status__in=['paid','partial'])
    total_revenue = revenue_qs.aggregate(t=Sum('amount_paid'))['t'] or 0
    revenue_by_type = revenue_qs.values('payment_for').annotate(t=Sum('amount_paid')).order_by('-t')
    expense_qs = Expense.objects.filter(gym=gym, expense_date__range=[p_start,p_end])
    total_expenses = expense_qs.aggregate(t=Sum('amount'))['t'] or 0
    exp_by_cat = expense_qs.values('category').annotate(t=Sum('amount')).order_by('-t')
    net_profit = total_revenue - total_expenses
    profit_margin = (net_profit/total_revenue*100) if total_revenue > 0 else 0
    billed = Payment.objects.filter(gym=gym, due_date__range=[p_start,p_end]).aggregate(t=Sum('amount_due'))['t'] or 0
    collected_of_billed = Payment.objects.filter(gym=gym, due_date__range=[p_start,p_end]).aggregate(t=Sum('amount_paid'))['t'] or 0
    collection_rate = (collected_of_billed/billed*100) if billed > 0 else 0
    transactions = (Payment.objects.filter(gym=gym, payment_date__range=[p_start, p_end])
                    .select_related('member').order_by('-payment_date','-created_at'))
    return render(request,'gym/reports.html',{'yr':yr,'mo':mo,'p_start':p_start,'p_end':p_end,
        'total_revenue':total_revenue,'total_expenses':total_expenses,'net_profit':net_profit,'profit_margin':profit_margin,
        'revenue_by_type':revenue_by_type,'exp_by_cat':exp_by_cat,'collection_rate':collection_rate,
        'billed':billed,'collected_of_billed':collected_of_billed,'months':months,
        'custom_range':custom_range,'start_str':p_start.isoformat(),'end_str':p_end.isoformat(),
        'transactions':transactions})


@login_required
@owner_required
def advanced_reports(request):
    """Deeper analytics: member movement, churn/at-risk, retention, plan mix,
    add-on attach rate, ARPM, payment-method split, trends, top members."""
    gym = get_gym(request); today = date.today()
    p_start, p_end, custom_range, yr, mo, months = _period(request)

    revenue_qs = Payment.objects.filter(gym=gym, payment_date__range=[p_start,p_end], status__in=['paid','partial'])
    total_revenue = revenue_qs.aggregate(t=Sum('amount_paid'))['t'] or 0
    revenue_by_method = revenue_qs.values('method').annotate(t=Sum('amount_paid')).order_by('-t')
    expense_qs = Expense.objects.filter(gym=gym, expense_date__range=[p_start,p_end])
    exp_by_cat = expense_qs.values('category').annotate(t=Sum('amount')).order_by('-t')
    exp_max = max([e['t'] for e in exp_by_cat], default=0) or 1
    salary_expense = EmployeeSalaryPayment.objects.filter(gym=gym, paid_date__range=[p_start,p_end]).aggregate(t=Sum('net_amount'))['t'] or 0

    # 6-month revenue vs expense trend
    trend = []; trend_max = 1
    for i in range(5,-1,-1):
        ms = (today.replace(day=1) - relativedelta(months=i)); me = ms + relativedelta(months=1) - timedelta(days=1)
        rev = Payment.objects.filter(gym=gym, payment_date__range=[ms,me], status__in=['paid','partial']).aggregate(t=Sum('amount_paid'))['t'] or 0
        exp = Expense.objects.filter(gym=gym, expense_date__range=[ms,me]).aggregate(t=Sum('amount'))['t'] or 0
        trend_max = max(trend_max, rev, exp)
        trend.append({'label': ms.strftime('%b'), 'revenue': rev, 'expense': exp, 'profit': rev-exp})
    for t in trend:
        t['rev_pct'] = round(t['revenue']/trend_max*100, 1); t['exp_pct'] = round(t['expense']/trend_max*100, 1)

    # Active plan distribution
    plan_dist = (MembershipRecord.objects.filter(gym=gym, status='active', end_date__gte=today)
                 .values('plan__name','custom_plan_name').annotate(c=Count('id')).order_by('-c'))
    plan_rows = []; pd_total = sum(p['c'] for p in plan_dist) or 1
    for p in plan_dist:
        name = p['plan__name'] or p['custom_plan_name'] or 'Custom'
        plan_rows.append({'name': name, 'count': p['c'], 'pct': round(p['c']/pd_total*100, 1)})

    # Top members
    top_spenders = (revenue_qs.values('member__id','member__full_name')
                    .annotate(total=Sum('amount_paid')).order_by('-total')[:10])

    # ── Member movement in the period ──
    joined   = Member.objects.filter(gym=gym, join_date__range=[p_start,p_end]).count()
    left     = Member.objects.filter(gym=gym, status='left', left_date__range=[p_start,p_end]).count()
    net_change = joined - left
    active_total   = Member.objects.filter(gym=gym, status='active').count()
    expired_total  = Member.objects.filter(gym=gym, status='expired').count()
    # Retention / churn: members at the start vs left during period
    base_members = Member.objects.filter(gym=gym, join_date__lt=p_start).exclude(status='left').count() or 0
    churn_rate = (left / base_members * 100) if base_members > 0 else 0
    retention_rate = 100 - churn_rate if base_members > 0 else 0

    # ── At-risk members: active but no check-in in 14+ days ──
    cutoff = today - timedelta(days=14)
    active_members = Member.objects.filter(gym=gym, status='active')
    at_risk = []
    recent_ids = set(AttendanceLog.objects.filter(gym=gym, date__gte=cutoff, is_present=True)
                     .values_list('member_id', flat=True))
    for mem in active_members.only('id','full_name','phone'):
        if mem.id not in recent_ids:
            last = AttendanceLog.objects.filter(gym=gym, member=mem, is_present=True).order_by('-date').first()
            at_risk.append({'id':mem.id,'name':mem.full_name,'phone':mem.phone,
                            'last': last.date if last else None,
                            'days': (today-last.date).days if last else None})
    at_risk.sort(key=lambda x: (x['days'] is not None, x['days'] or 0), reverse=True)
    at_risk = at_risk[:25]

    # ── Add-on attach rate ──
    members_with_addon = MemberAddOn.objects.filter(gym=gym, status='active').values('member').distinct().count()
    attach_rate = (members_with_addon / active_total * 100) if active_total > 0 else 0

    # ── ARPM: average revenue per active member (this period) ──
    arpm = (total_revenue / active_total) if active_total > 0 else 0

    # ── Attendance: total check-ins + unique visitors in period ──
    checkins = AttendanceLog.objects.filter(gym=gym, date__range=[p_start,p_end], is_present=True)
    total_checkins = checkins.count()
    unique_visitors = checkins.values('member').distinct().count()
    defaulter_total = Payment.objects.filter(gym=gym, status='overdue').values('member').distinct().count()

    return render(request,'gym/advanced_reports.html',{'yr':yr,'mo':mo,'p_start':p_start,'p_end':p_end,
        'months':months,'custom_range':custom_range,'start_str':p_start.isoformat(),'end_str':p_end.isoformat(),
        'revenue_by_method':revenue_by_method,'exp_by_cat':exp_by_cat,'exp_max':exp_max,'salary_expense':salary_expense,
        'trend':trend,'plan_rows':plan_rows,'top_spenders':top_spenders,
        'joined':joined,'left':left,'net_change':net_change,'active_total':active_total,'expired_total':expired_total,
        'churn_rate':churn_rate,'retention_rate':retention_rate,'base_members':base_members,
        'at_risk':at_risk,'attach_rate':attach_rate,'members_with_addon':members_with_addon,
        'arpm':arpm,'total_revenue':total_revenue,'total_checkins':total_checkins,
        'unique_visitors':unique_visitors,'defaulter_total':defaulter_total})


@login_required
@owner_required
def export_transactions(request):
    """Download the transaction log as a CSV (opens directly in Excel)."""
    import csv
    from django.http import HttpResponse
    from datetime import datetime as _dt
    gym = get_gym(request)
    today = date.today()
    start_str = request.GET.get('start',''); end_str = request.GET.get('end','')
    try:
        p_start = _dt.strptime(start_str, '%Y-%m-%d').date() if start_str else today.replace(day=1)
        p_end   = _dt.strptime(end_str, '%Y-%m-%d').date() if end_str else today
    except ValueError:
        p_start = today.replace(day=1); p_end = today
    if p_end < p_start:
        p_start, p_end = p_end, p_start
    sym = gym.currency_symbol
    rows = (Payment.objects.filter(gym=gym, payment_date__range=[p_start, p_end])
            .select_related('member').order_by('payment_date','created_at'))
    resp = HttpResponse(content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="transactions_{p_start}_{p_end}.csv"'
    w = csv.writer(resp)
    w.writerow(['Date','Member','Phone','Payment For','Method','Status',
                f'Amount Due ({sym})', f'Amount Paid ({sym})', f'Balance ({sym})', 'Transaction ID','Notes'])
    tot_due = tot_paid = 0
    for p in rows:
        tot_due += float(p.amount_due or 0); tot_paid += float(p.amount_paid or 0)
        w.writerow([p.payment_date.strftime('%Y-%m-%d'), p.member.full_name, p.member.phone,
                    p.get_payment_for_display(), p.get_method_display(), p.get_status_display(),
                    f'{p.amount_due:.2f}', f'{p.amount_paid:.2f}', f'{p.balance_due:.2f}',
                    p.transaction_id or '', (p.notes or '').replace('\n',' ')])
    w.writerow([])
    w.writerow(['', '', '', '', '', 'TOTAL', f'{tot_due:.2f}', f'{tot_paid:.2f}', f'{tot_due-tot_paid:.2f}', '', ''])
    return resp


# ─────────────────────────────────────────────
# WHATSAPP
# ─────────────────────────────────────────────
@login_required
def whatsapp_generator(request):
    gym = get_gym(request)
    members = Member.objects.filter(gym=gym, status='active').order_by('full_name')
    templates = WhatsAppTemplate.objects.filter(gym=gym)
    sel_member = None; rendered = None; wa_link = None
    pre_pk = request.GET.get('member')
    if pre_pk:
        sel_member = Member.objects.filter(gym=gym, pk=pre_pk).first()
    if request.method == 'POST':
        mid = request.POST.get('member_id'); tid = request.POST.get('template_id'); custom = request.POST.get('custom_text','').strip()
        if mid:
            sel_member = t404(Member, gym, pk=mid)
            overdue = sel_member.payments.filter(status__in=['overdue','partial','pending']).first()
            active_mem = sel_member.active_membership
            if tid:
                tpl = t404(WhatsAppTemplate, gym, pk=tid)
                rendered = tpl.render(member=sel_member, amount_due=overdue.balance_due if overdue else None,
                    due_date=overdue.due_date if overdue else None, expiry_date=active_mem.end_date if active_mem else None,
                    plan_name=active_mem.plan_display_name if active_mem else None, gym=gym)
            elif custom:
                rendered = custom
            if rendered and sel_member.phone:
                import urllib.parse
                phone = sel_member.phone.replace(' ','').replace('-','')
                if not phone.startswith('+'): phone = '+92' + phone.lstrip('0')
                wa_link = f"https://wa.me/{phone}?text={urllib.parse.quote(rendered)}"
    return render(request,'gym/whatsapp_generator.html',{'members':members,'templates':templates,'sel_member':sel_member,'rendered':rendered,'wa_link':wa_link})

@login_required
def whatsapp_templates(request):
    gym = get_gym(request)
    return render(request,'gym/whatsapp_templates.html',{'templates':WhatsAppTemplate.objects.filter(gym=gym)})

@login_required
def whatsapp_template_add(request):
    gym = get_gym(request)
    pk = request.GET.get('edit')
    instance = WhatsAppTemplate.objects.filter(gym=gym, pk=pk).first() if pk else None
    if request.method == 'POST':
        form = WhatsAppTemplateForm(request.POST, instance=instance)
        if form.is_valid():
            t = form.save(commit=False); t.gym = gym; t.save()
            messages.success(request,'Template saved.')
            return redirect('whatsapp_templates')
    else:
        form = WhatsAppTemplateForm(instance=instance)
    return render(request,'gym/whatsapp_template_form.html',{'form':form,'instance':instance})


# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────
@login_required
def subscription_expired(request):
    gym = None
    try:
        gym = get_gym(request)
    except Exception:
        pass
    return render(request, 'gym/subscription_expired.html', {'gym': gym})


@login_required
def set_theme(request, theme):
    gym = get_gym(request)
    valid = [c[0] for c in Gym.THEME_CHOICES]
    if theme in valid:
        gym.theme = theme
        gym.save(update_fields=['theme'])
        messages.success(request, f'Theme changed to {dict(Gym.THEME_CHOICES)[theme]}.')
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required
@owner_required
def gym_settings(request):
    gym = get_gym(request)
    if request.method == 'POST':
        form = GymForm(request.POST, instance=gym)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.currency = obj.currency_symbol  # keep symbol field in sync for display
            obj.save()
            messages.success(request,'Settings saved.')
            return redirect('gym_settings')
    else:
        form = GymForm(instance=gym)
    return render(request,'gym/settings.html',{'form':form,'profile':gym})


# ─────────────────────────────────────────────
# AJAX
# ─────────────────────────────────────────────
@login_required
def ajax_plan_price(request):
    gym = get_gym(request)
    plan = MembershipPlan.objects.filter(gym=gym, pk=request.GET.get('plan_id')).first()
    if plan:
        return JsonResponse({'price':str(plan.price),'includes_trainer':plan.includes_trainer,'includes_locker':plan.includes_locker,'includes_cardio':plan.includes_cardio})
    return JsonResponse({'price':'0'})
