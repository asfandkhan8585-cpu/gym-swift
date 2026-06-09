from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),
    path('register/', views.register_view, name='register'),
    path('elevate/',  views.elevate,       name='elevate'),
    path('lock/',     views.lock_owner,    name='lock_owner'),
    path('subscription-expired/', views.subscription_expired, name='subscription_expired'),

    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Members
    path('members/',                          views.member_list,        name='member_list'),
    path('members/former/',                   views.former_members,     name='former_members'),
    path('members/add/',                      views.member_add,         name='member_add'),
    path('members/<int:pk>/',                 views.member_detail,      name='member_detail'),
    path('members/<int:pk>/print/',           views.member_print,       name='member_print'),
    path('members/<int:pk>/edit/',            views.member_edit,        name='member_edit'),
    path('members/<int:pk>/delete/',          views.member_delete,      name='member_delete'),
    path('members/<int:pk>/restore/',         views.member_restore,     name='member_restore'),
    path('members/<int:pk>/membership/',      views.assign_membership,  name='assign_membership'),
    path('members/<int:pk>/addon/',           views.assign_addon,       name='assign_addon'),
    path('members/<int:pk>/locker/',          views.assign_locker,      name='assign_locker'),
    path('members/<int:pk>/locker/release/',  views.release_locker,     name='release_locker'),

    # Attendance (members)
    path('attendance/',                       views.attendance_today,   name='attendance_today'),
    path('attendance/mark/',                  views.mark_attendance,    name='mark_attendance'),
    path('attendance/<int:pk>/history/',      views.attendance_history, name='attendance_history'),

    # Payments
    path('payments/',                         views.payment_list,       name='payment_list'),
    path('payments/add/',                     views.payment_add,        name='payment_add'),
    path('payments/add/<int:member_pk>/',     views.payment_add,        name='payment_add_member'),
    path('payments/defaulters/',              views.defaulter_list,     name='defaulter_list'),

    # Expenses
    path('expenses/',                         views.expense_list,       name='expense_list'),
    path('expenses/add/',                     views.expense_add,        name='expense_add'),
    path('expenses/<int:pk>/edit/',           views.expense_edit,       name='expense_edit'),
    path('expenses/<int:pk>/delete/',         views.expense_delete,     name='expense_delete'),

    # Employees
    path('employees/',                        views.employee_list,      name='employee_list'),
    path('employees/add/',                    views.employee_add,       name='employee_add'),
    path('employees/<int:pk>/',               views.employee_detail,    name='employee_detail'),
    path('employees/<int:pk>/edit/',          views.employee_edit,      name='employee_edit'),
    path('employees/<int:pk>/delete/',        views.employee_delete,    name='employee_delete'),
    path('employees/<int:pk>/salary/',        views.pay_salary,         name='pay_salary'),
    path('employees/attendance/',             views.employee_attendance,name='employee_attendance'),
    path('employees/attendance/mark/',        views.mark_employee_attendance, name='mark_employee_attendance'),

    # Lockers
    path('lockers/',                          views.locker_list,        name='locker_list'),
    path('lockers/add/',                      views.locker_add,         name='locker_add'),
    path('lockers/<int:pk>/edit/',            views.locker_edit,        name='locker_edit'),
    path('lockers/<int:pk>/delete/',          views.locker_delete,      name='locker_delete'),

    # Plans & Add-Ons
    path('plans/',                            views.plan_list,          name='plan_list'),
    path('plans/add/',                        views.plan_add,           name='plan_add'),
    path('plans/<int:pk>/edit/',              views.plan_edit,          name='plan_edit'),
    path('plans/<int:pk>/delete/',            views.plan_delete,        name='plan_delete'),
    path('addons/',                           views.addon_list,         name='addon_list'),
    path('addons/add/',                       views.addon_add,          name='addon_add'),
    path('addons/<int:pk>/edit/',             views.addon_edit,         name='addon_edit'),
    path('addons/<int:pk>/delete/',           views.addon_delete,       name='addon_delete'),

    # Reports
    path('reports/',                          views.reports,            name='reports'),
    path('reports/advanced/',                 views.advanced_reports,   name='advanced_reports'),
    path('reports/export/',                   views.export_transactions, name='export_transactions'),

    # WhatsApp
    path('whatsapp/',                         views.whatsapp_generator, name='whatsapp_generator'),
    path('whatsapp/templates/',               views.whatsapp_templates, name='whatsapp_templates'),
    path('whatsapp/templates/add/',           views.whatsapp_template_add, name='whatsapp_template_add'),
    path('whatsapp/templates/<int:pk>/delete/', views.whatsapp_template_delete, name='whatsapp_template_delete'),

    # Settings
    path('settings/',                         views.gym_settings,       name='gym_settings'),
    path('set-theme/<str:theme>/',            views.set_theme,          name='set_theme'),

    # AJAX
    path('ajax/plan-price/',                  views.ajax_plan_price,    name='ajax_plan_price'),
]
