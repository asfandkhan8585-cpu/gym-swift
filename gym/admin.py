from django.contrib import admin
from .models import (
    Gym, UserProfile, Member, MembershipPlan, MembershipRecord, AddOn, MemberAddOn,
    Locker, LockerAssignment, Employee, EmployeeAttendance, EmployeeSalaryPayment,
    AttendanceLog, Payment, Expense, WhatsAppTemplate
)

@admin.register(Gym)
class GymAdmin(admin.ModelAdmin):
    list_display = ['name','owner','city','subscription_status','subscription_until','subscription_fee','created_at']
    list_filter  = ['subscription_status','created_at']
    search_fields = ['name','owner__username','phone','email']
    list_editable = ['subscription_status','subscription_until','subscription_fee']
    actions = ['extend_one_month', 'mark_active', 'mark_suspended']
    fieldsets = (
        ('Gym', {'fields': ('name','owner','tagline','city','address','phone','whatsapp','email')}),
        ('Localization', {'fields': ('currency_code','currency','theme','gents_timing','ladies_timing')}),
        ('Security', {'fields': ('owner_key',)}),
        ('Subscription (provider-managed)', {'fields': ('subscription_status','subscription_until','subscription_fee','subscription_notes')}),
    )

    @admin.action(description="Extend subscription by 1 month")
    def extend_one_month(self, request, queryset):
        from datetime import date
        try:
            from dateutil.relativedelta import relativedelta
            for g in queryset:
                base = g.subscription_until if (g.subscription_until and g.subscription_until > date.today()) else date.today()
                g.subscription_until = base + relativedelta(months=1)
                g.subscription_status = 'active'
                g.save(update_fields=['subscription_until','subscription_status'])
        except ImportError:
            pass
        self.message_user(request, f"Extended {queryset.count()} gym(s) by one month.")

    @admin.action(description="Mark ACTIVE")
    def mark_active(self, request, queryset):
        queryset.update(subscription_status='active')

    @admin.action(description="Mark SUSPENDED (block access)")
    def mark_suspended(self, request, queryset):
        queryset.update(subscription_status='suspended')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user','gym','is_owner','role']

@admin.register(MembershipPlan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name','gym','duration','price','is_active']
    list_filter  = ['gym','is_active']

@admin.register(AddOn)
class AddOnAdmin(admin.ModelAdmin):
    list_display = ['name','gym','addon_type','price','billing_cycle']
    list_filter  = ['gym','addon_type']

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display  = ['full_name','gym','phone','role','status','monthly_salary']
    list_filter   = ['gym','role','status']
    search_fields = ['full_name','phone','cnic']

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display  = ['full_name','gym','phone','cnic','shift','status','join_date']
    list_filter   = ['gym','status','shift']
    search_fields = ['full_name','phone','cnic']

@admin.register(MembershipRecord)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['member','gym','plan','start_date','end_date','status']
    list_filter  = ['gym','status']

@admin.register(Locker)
class LockerAdmin(admin.ModelAdmin):
    list_display = ['locker_number','gym','zone','status','monthly_rate']
    list_filter  = ['gym','zone','status']

admin.site.register(LockerAssignment)
admin.site.register(MemberAddOn)
admin.site.register(EmployeeAttendance)
admin.site.register(EmployeeSalaryPayment)

@admin.register(AttendanceLog)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ['member','gym','date','is_present','check_in_time']
    list_filter   = ['gym','date','is_present']

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ['member','gym','amount_paid','amount_due','method','status','payment_date']
    list_filter   = ['gym','status','method']

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['title','gym','category','amount','expense_date']
    list_filter  = ['gym','category']

admin.site.register(WhatsAppTemplate)
