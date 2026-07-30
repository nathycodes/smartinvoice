from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import (
    SignUpForm, CommandInputForm, CustomerForm, ProductForm,
    PaymentForm, InvoiceStatusForm,
)
from .models import Business, Customer, Product, Invoice, InvoiceItem, Payment, CommandLog
from .parser import parse_command


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = User.objects.create_user(
            username=data["username"], email=data["email"], password=data["password"]
        )
        Business.objects.create(
            owner=user,
            business_name=data["business_name"],
            phone_number=data["phone_number"],
            email=data["email"],
        )
        login(request, user)
        messages.success(request, "Welcome! Your business account has been created.")
        return redirect("dashboard")
    return render(request, "invoices/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        error = "Invalid username or password."
    return render(request, "invoices/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("login")


def _get_business(request):
    return get_object_or_404(Business, owner=request.user)


def _normalize_lookup_text(text):
    """Normalize product names for safe case-insensitive matching."""
    return " ".join((text or "").split()).casefold()


def _get_product_index(business):
    """Build a simple in-memory product lookup keyed by normalized product name."""
    return {
        _normalize_lookup_text(product.name): product
        for product in Product.objects.filter(business=business, is_active=True)
    }


def _apply_saved_product_prices(items, product_index):
    """
    Fill missing item prices from saved products.

    Returns a list of descriptions that still could not be resolved.
    """

    unresolved = []

    for item in items:
        product = product_index.get(_normalize_lookup_text(item.description))
        if product is not None:
            if item.unit_price <= 0:
                item.unit_price = product.unit_price
            if not item.unit or item.unit == "unit":
                item.unit = product.unit
        elif item.unit_price <= 0:
            unresolved.append(item.description)

    return unresolved


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    business = _get_business(request)
    invoices = Invoice.objects.filter(business=business)

    total_invoices = invoices.count()
    total_customers = Customer.objects.filter(business=business).count()

    total_revenue = sum((inv.total_amount for inv in invoices), 0)
    total_outstanding = sum(
        (inv.balance_due for inv in invoices if inv.status not in ("PAID", "CANCELLED")), 0
    )

    status_counts = {
        choice[0]: invoices.filter(status=choice[0]).count() for choice in Invoice.STATUS_CHOICES
    }

    recent_invoices = invoices.order_by("-created_at")[:6]
    recent_commands = CommandLog.objects.filter(business=business).order_by("-created_at")[:5]

    context = {
        "business": business,
        "total_invoices": total_invoices,
        "total_customers": total_customers,
        "total_revenue": total_revenue,
        "total_outstanding": total_outstanding,
        "status_counts": status_counts,
        "recent_invoices": recent_invoices,
        "recent_commands": recent_commands,
    }
    return render(request, "invoices/dashboard.html", context)


# ---------------------------------------------------------------------------
# Smart Invoice Creation (Voice / Text)
# ---------------------------------------------------------------------------

@login_required
def create_invoice_smart(request):
    business = _get_business(request)
    form = CommandInputForm(request.POST or None)
    parsed_preview = None
    parsed_dict = None

    if request.method == "POST" and form.is_valid():
        raw_text = form.cleaned_data["command_text"]
        input_type = form.cleaned_data["input_type"]
        parsed = parse_command(raw_text)
        product_index = _get_product_index(business)
        unresolved = _apply_saved_product_prices(parsed.items, product_index)

        if unresolved:
            for description in unresolved:
                parsed.errors.append(f"Saved product price not found for '{description}'.")
            parsed.success = False

        parsed_dict = parsed.as_dict()

        log = CommandLog.objects.create(
            business=business,
            user=request.user,
            input_type=input_type,
            raw_text=raw_text,
            parsed_successfully=parsed.success,
            parsed_data=parsed_dict,
            error_message="; ".join(parsed.errors) if parsed.errors else "",
        )

        if parsed.success:
            customer, _ = Customer.objects.get_or_create(
                business=business, name=parsed.customer_name
            )
            due_date = None
            if parsed.due_in_days is not None:
                due_date = timezone.now().date() + timedelta(days=parsed.due_in_days)

            invoice = Invoice.objects.create(
                business=business,
                customer=customer,
                due_date=due_date,
                discount=0,
                source=input_type,
                raw_command_text=raw_text,
                created_by=request.user,
            )

            for item in parsed.items:
                product = product_index.get(_normalize_lookup_text(item.description))
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )

            if parsed.discount_percent:
                subtotal = invoice.subtotal
                invoice.discount = subtotal * (parsed.discount_percent / 100)
                invoice.save()

            log.resulting_invoice = invoice
            log.save()

            messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
            return redirect("invoice_detail", pk=invoice.pk)
        else:
            parsed_preview = parsed_dict

    return render(
        request,
        "invoices/create_invoice_smart.html",
        {"form": form, "parsed_preview": parsed_preview, "parsed_dict": parsed_dict},
    )


@login_required
def create_invoice_manual(request):
    business = _get_business(request)
    customers = Customer.objects.filter(business=business)
    products = Product.objects.filter(business=business, is_active=True)
    product_index = _get_product_index(business)

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        customer = get_object_or_404(Customer, pk=customer_id, business=business)
        due_date = request.POST.get("due_date") or None

        descriptions = request.POST.getlist("item_description")
        quantities = request.POST.getlist("item_quantity")
        prices = request.POST.getlist("item_price")

        for desc, qty, price in zip(descriptions, quantities, prices):
            if not desc or not qty:
                continue

            product = product_index.get(_normalize_lookup_text(desc))
            resolved_price = price

            if (resolved_price is None or str(resolved_price).strip() == "" or str(resolved_price).strip() == "0") and product:
                resolved_price = product.unit_price

            try:
                resolved_price_value = Decimal(str(resolved_price))
            except (InvalidOperation, TypeError, ValueError):
                resolved_price_value = Decimal("0")

            if resolved_price_value <= 0:
                continue

            if "invoice" not in locals():
                invoice = Invoice.objects.create(
                    business=business,
                    customer=customer,
                    due_date=due_date,
                    source="MANUAL",
                    created_by=request.user,
                )

            InvoiceItem.objects.create(
                invoice=invoice,
                product=product,
                description=desc,
                quantity=qty,
                unit_price=resolved_price_value,
            )

        if "invoice" not in locals():
            messages.error(request, "Please add at least one item with a valid price or a saved product name.")
            return render(
                request,
                "invoices/create_invoice_manual.html",
                {"customers": customers, "products": products},
            )

        messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
        return redirect("invoice_detail", pk=invoice.pk)

    return render(
        request,
        "invoices/create_invoice_manual.html",
        {"customers": customers, "products": products},
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@login_required
def invoice_list(request):
    business = _get_business(request)
    invoices = Invoice.objects.filter(business=business)

    status = request.GET.get("status")
    query = request.GET.get("q")
    if status:
        invoices = invoices.filter(status=status)
    if query:
        invoices = invoices.filter(
            Q(invoice_number__icontains=query) | Q(customer__name__icontains=query)
        )

    return render(
        request,
        "invoices/invoice_list.html",
        {"invoices": invoices, "status_choices": Invoice.STATUS_CHOICES, "status": status, "query": query or ""},
    )


@login_required
def invoice_detail(request, pk):
    business = _get_business(request)
    invoice = get_object_or_404(Invoice, pk=pk, business=business)
    payment_form = PaymentForm()
    status_form = InvoiceStatusForm(instance=invoice)
    return render(
        request,
        "invoices/invoice_detail.html",
        {"invoice": invoice, "payment_form": payment_form, "status_form": status_form},
    )


@login_required
def invoice_print(request, pk):
    business = _get_business(request)
    invoice = get_object_or_404(Invoice, pk=pk, business=business)
    return render(request, "invoices/invoice_print.html", {"invoice": invoice, "business": business})


@login_required
def add_payment(request, pk):
    business = _get_business(request)
    invoice = get_object_or_404(Invoice, pk=pk, business=business)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.invoice = invoice
            payment.recorded_by = request.user
            payment.save()

            if invoice.balance_due <= 0:
                invoice.status = "PAID"
            elif invoice.amount_paid > 0:
                invoice.status = "PARTIALLY_PAID"
            invoice.save()
            messages.success(request, "Payment recorded successfully.")
    return redirect("invoice_detail", pk=pk)


@login_required
def update_invoice_status(request, pk):
    business = _get_business(request)
    invoice = get_object_or_404(Invoice, pk=pk, business=business)
    if request.method == "POST":
        form = InvoiceStatusForm(request.POST, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, "Invoice updated.")
    return redirect("invoice_detail", pk=pk)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@login_required
def customer_list(request):
    business = _get_business(request)
    customers = Customer.objects.filter(business=business).annotate(invoice_count=Count("invoices"))
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        customer = form.save(commit=False)
        customer.business = business
        customer.save()
        messages.success(request, "Customer added.")
        return redirect("customer_list")
    return render(request, "invoices/customer_list.html", {"customers": customers, "form": form})


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@login_required
def product_list(request):
    business = _get_business(request)
    products = Product.objects.filter(business=business)
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.business = business
        product.save()
        messages.success(request, "Product added.")
        return redirect("product_list")
    return render(request, "invoices/product_list.html", {"products": products, "form": form})


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@login_required
def reports(request):
    business = _get_business(request)
    invoices = Invoice.objects.filter(business=business)

    total_revenue = sum((inv.total_amount for inv in invoices), 0)
    total_collected = sum((inv.amount_paid for inv in invoices), 0)
    total_outstanding = total_revenue - total_collected

    by_status = {choice[0]: invoices.filter(status=choice[0]).count() for choice in Invoice.STATUS_CHOICES}

    top_customers = (
        Customer.objects.filter(business=business)
        .annotate(num_invoices=Count("invoices"))
        .order_by("-num_invoices")[:5]
    )

    command_logs = CommandLog.objects.filter(business=business).order_by("-created_at")[:20]
    voice_count = CommandLog.objects.filter(business=business, input_type="VOICE").count()
    text_count = CommandLog.objects.filter(business=business, input_type="TEXT").count()
    success_count = CommandLog.objects.filter(business=business, parsed_successfully=True).count()
    total_commands = CommandLog.objects.filter(business=business).count()

    context = {
        "total_revenue": total_revenue,
        "total_collected": total_collected,
        "total_outstanding": total_outstanding,
        "by_status": by_status,
        "top_customers": top_customers,
        "command_logs": command_logs,
        "voice_count": voice_count,
        "text_count": text_count,
        "success_count": success_count,
        "total_commands": total_commands,
    }
    return render(request, "invoices/reports.html", context)


@login_required
def command_log_list(request):
    business = _get_business(request)
    logs = CommandLog.objects.filter(business=business).order_by("-created_at")
    return render(request, "invoices/command_log_list.html", {"logs": logs})
