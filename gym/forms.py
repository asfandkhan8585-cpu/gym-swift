from django import forms
from .models import (
    Gym, Member, MembershipPlan, MembershipRecord, AddOn, MemberAddOn,
    Locker, LockerAssignment, Employee, EmployeeAttendance,
    EmployeeSalaryPayment, AttendanceLog, Payment, Expense, WhatsAppTemplate
)


class GymForm(forms.ModelForm):
    class Meta:
        model  = Gym
        fields = ['name','tagline','address','city','phone','whatsapp','email',
                  'bank_name','bank_account','easypaisa_no','jazzcash_no',
                  'gents_timing','ladies_timing','currency_code','theme','owner_key']
        widgets = {'owner_key': forms.TextInput(attrs={'maxlength':'4','pattern':'[0-9]{4}','inputmode':'numeric'})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .currencies import CURRENCY_CHOICES
        self.fields['currency_code'] = forms.ChoiceField(choices=CURRENCY_CHOICES, label="Currency")
        self.fields['currency_code'].initial = self.instance.currency_code if self.instance else 'PKR'


class MembershipPlanForm(forms.ModelForm):
    class Meta:
        model  = MembershipPlan
        fields = ['name','duration','custom_days','price','description',
                  'includes_cardio','includes_weights','includes_trainer',
                  'includes_locker','includes_steam','notes','is_active']
        widgets = {'description':forms.Textarea(attrs={'rows':2}),'notes':forms.Textarea(attrs={'rows':2})}


class AddOnForm(forms.ModelForm):
    class Meta:
        model  = AddOn
        fields = ['name','addon_type','price','billing_cycle','description','is_active']
        widgets = {'description':forms.Textarea(attrs={'rows':2})}


class MemberForm(forms.ModelForm):
    """gym kwarg scopes trainer/referral dropdowns to this gym only."""
    class Meta:
        model  = Member
        fields = ['full_name','phone','email','cnic','date_of_birth','gender',
                  'blood_group','address','city','occupation',
                  'emergency_name','emergency_phone','emergency_relation',
                  'medical_conditions','fitness_goal','shift','status','join_date',
                  'assigned_trainer','referred_by','notes','photo']
        widgets = {
            'date_of_birth':forms.DateInput(attrs={'type':'date'}),
            'join_date':forms.DateInput(attrs={'type':'date'}),
            'medical_conditions':forms.Textarea(attrs={'rows':2}),
            'notes':forms.Textarea(attrs={'rows':2}),
            'address':forms.Textarea(attrs={'rows':2}),
        }
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._gym = gym
        if gym:
            self.fields['assigned_trainer'].queryset = Employee.objects.filter(gym=gym, role='trainer', status='active')
            self.fields['referred_by'].queryset = Member.objects.filter(gym=gym)

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if phone and self._gym:
            qs = Member.objects.filter(gym=self._gym, phone=phone)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                existing = qs.first()
                raise forms.ValidationError(
                    f'This phone number is already registered to "{existing.full_name}" in your gym. '
                    f'Each member needs a unique phone number.')
        return phone


class MembershipRecordForm(forms.ModelForm):
    class Meta:
        model  = MembershipRecord
        fields = ['plan','custom_plan_name','custom_duration_days','custom_price',
                  'start_date','amount_paid','uses_cardio_equipment','uses_free_weights',
                  'has_personal_trainer','trainer','trainer_sessions_per_month',
                  'has_locker','has_steam_room','notes']
        widgets = {'start_date':forms.DateInput(attrs={'type':'date'}),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['plan'].queryset = MembershipPlan.objects.filter(gym=gym, is_active=True)
            self.fields['plan'].required = False
            self.fields['trainer'].queryset = Employee.objects.filter(gym=gym, role='trainer')
            self.fields['trainer'].required = False
        self.fields['trainer_sessions_per_month'].required = False
        self.fields['custom_duration_days'].required = False
        self.fields['custom_price'].required = False

    def clean_trainer_sessions_per_month(self):
        return self.cleaned_data.get('trainer_sessions_per_month') or 0


class MemberAddOnForm(forms.ModelForm):
    class Meta:
        model  = MemberAddOn
        fields = ['addon','start_date','end_date','quantity','rate','notes']
        widgets = {'start_date':forms.DateInput(attrs={'type':'date'}),'end_date':forms.DateInput(attrs={'type':'date'})}
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['addon'].queryset = AddOn.objects.filter(gym=gym, is_active=True)


class LockerForm(forms.ModelForm):
    class Meta:
        model  = Locker
        fields = ['locker_number','zone','monthly_rate','status','notes']
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._gym = gym

    def clean_locker_number(self):
        num = (self.cleaned_data.get('locker_number') or '').strip()
        if num and self._gym:
            qs = Locker.objects.filter(gym=self._gym, locker_number=num)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f'Locker number "{num}" already exists in your gym.')
        return num


class LockerAssignmentForm(forms.ModelForm):
    class Meta:
        model  = LockerAssignment
        fields = ['member','locker','assigned_date','expiry_date','monthly_rate','amount_paid','deposit_paid','key_number','notes']
        widgets = {'assigned_date':forms.DateInput(attrs={'type':'date'}),'expiry_date':forms.DateInput(attrs={'type':'date'})}
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['member'].queryset = Member.objects.filter(gym=gym)
            self.fields['locker'].queryset = Locker.objects.filter(gym=gym, status='available')


class EmployeeForm(forms.ModelForm):
    class Meta:
        model  = Employee
        fields = ['full_name','phone','email','cnic','date_of_birth','blood_group',
                  'address','role','status','join_date','monthly_salary','salary_day',
                  'emergency_name','emergency_phone','emergency_relation',
                  'specialization','certifications','experience_years','per_session_rate','notes','photo']
        widgets = {
            'date_of_birth':forms.DateInput(attrs={'type':'date'}),
            'join_date':forms.DateInput(attrs={'type':'date'}),
            'certifications':forms.Textarea(attrs={'rows':2}),
            'address':forms.Textarea(attrs={'rows':2}),
            'notes':forms.Textarea(attrs={'rows':2}),
        }
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._gym = gym

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if phone and self._gym:
            qs = Employee.objects.filter(gym=self._gym, phone=phone)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                existing = qs.first()
                raise forms.ValidationError(
                    f'This phone number is already used by employee "{existing.full_name}". '
                    f'Each employee needs a unique phone number.')
        return phone


class EmployeeSalaryForm(forms.ModelForm):
    class Meta:
        model  = EmployeeSalaryPayment
        fields = ['employee','month','amount','bonus','deduction','method','paid_date','transaction_id','notes']
        widgets = {'month':forms.DateInput(attrs={'type':'date'}),'paid_date':forms.DateInput(attrs={'type':'date'}),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['employee'].queryset = Employee.objects.filter(gym=gym)


class PaymentForm(forms.ModelForm):
    class Meta:
        model  = Payment
        fields = ['member','membership_record','payment_for','amount_due','amount_paid','payment_date','due_date','method','transaction_id','notes']
        widgets = {'payment_date':forms.DateInput(attrs={'type':'date'}),'due_date':forms.DateInput(attrs={'type':'date'}),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['member'].queryset = Member.objects.filter(gym=gym)
            self.fields['membership_record'].queryset = MembershipRecord.objects.filter(gym=gym)
            self.fields['membership_record'].required = False


class ExpenseForm(forms.ModelForm):
    class Meta:
        model  = Expense
        fields = ['category','title','amount','expense_date','method','vendor','receipt_no','description','employee']
        widgets = {'expense_date':forms.DateInput(attrs={'type':'date'}),'description':forms.Textarea(attrs={'rows':2})}
    def __init__(self, *args, gym=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['employee'].queryset = Employee.objects.filter(gym=gym)
            self.fields['employee'].required = False


class WhatsAppTemplateForm(forms.ModelForm):
    class Meta:
        model  = WhatsAppTemplate
        fields = ['name','template_type','body','is_default']
        widgets = {'body':forms.Textarea(attrs={'rows':6})}
