import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Business(models.Model):
    """Represents an SME (the business using the platform)."""
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="business")
    business_name = models.CharField(max_length=150)
    business_address = models.CharField(max_length=255, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    default_currency = models.CharField(max_length=10, default="NGN")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name


class Customer(models.Model):
    """A customer/client that an SME issues invoices to."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """A product or service an SME sells, used to auto-fill invoice items."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=30, default="unit")  # e.g. bag, carton, piece, hour
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.unit})"


class Invoice(models.Model):
    """An invoice generated for a customer, via text or voice input."""

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("UNPAID", "Unpaid"),
        ("PARTIALLY_PAID", "Partially Paid"),
        ("PAID", "Paid"),
        ("OVERDUE", "Overdue"),
        ("CANCELLED", "Cancelled"),
    ]

    SOURCE_CHOICES = [
        ("TEXT", "Text Input"),
        ("VOICE", "Voice Input"),
        ("MANUAL", "Manual Form"),
    ]

    invoice_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="invoices")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="invoices")
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="UNPAID")
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="TEXT")
    raw_command_text = models.TextField(
        blank=True, help_text="The original text or transcribed voice command used to create this invoice."
    )
    notes = models.TextField(blank=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="invoices_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            prefix = "INV"
            today = timezone.now().strftime("%Y%m%d")
            count = Invoice.objects.filter(business=self.business).count() + 1
            self.invoice_number = f"{prefix}-{today}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.all()), Decimal("0"))

    @property
    def tax_amount(self):
        return (self.subtotal - Decimal(self.discount)) * (Decimal(self.tax_percent) / Decimal("100"))

    @property
    def total_amount(self):
        return (self.subtotal - Decimal(self.discount)) + self.tax_amount

    @property
    def amount_paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal("0"))

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"


class InvoiceItem(models.Model):
    """A line item within an invoice."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=150)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.description} x{self.quantity}"


class Payment(models.Model):
    """Records a payment made towards an invoice."""

    METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("POS", "POS / Card"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("OTHER", "Other"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="CASH")
    reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateField(default=timezone.now)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.amount}"


class CommandLog(models.Model):
    """
    Logs every voice or text command submitted by a user for NLP parsing,
    along with the parsed result and whether parsing succeeded.
    Supports auditability and helps refine the parsing engine.
    """

    INPUT_CHOICES = [("TEXT", "Text"), ("VOICE", "Voice")]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="command_logs")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    input_type = models.CharField(max_length=10, choices=INPUT_CHOICES)
    raw_text = models.TextField()
    parsed_successfully = models.BooleanField(default=False)
    parsed_data = models.JSONField(blank=True, null=True)
    resulting_invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="command_logs"
    )
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.input_type}] {self.raw_text[:40]}"
