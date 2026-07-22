from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Smart (voice/text) invoice creation
    path("invoices/new/smart/", views.create_invoice_smart, name="create_invoice_smart"),
    path("invoices/new/manual/", views.create_invoice_manual, name="create_invoice_manual"),

    # Invoices
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/print/", views.invoice_print, name="invoice_print"),
    path("invoices/<int:pk>/pay/", views.add_payment, name="add_payment"),
    path("invoices/<int:pk>/status/", views.update_invoice_status, name="update_invoice_status"),

    # Customers & Products
    path("customers/", views.customer_list, name="customer_list"),
    path("products/", views.product_list, name="product_list"),

    # Reports & Command Logs
    path("reports/", views.reports, name="reports"),
    path("command-logs/", views.command_log_list, name="command_log_list"),
]
