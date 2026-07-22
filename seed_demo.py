"""
seed_demo.py — populates the database with a realistic Nigerian SME
(a provisions/electronics retailer) so the system can be demonstrated
and screenshotted with real-looking data.

Run with: python3 manage.py shell < seed_demo.py
"""
import os
import django
import sys
from datetime import timedelta

sys.path.insert(0, "/home/claude/smartinvoice")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartinvoice.settings")
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone
from invoices.models import Business, Customer, Product, Invoice, InvoiceItem, Payment, CommandLog
from invoices.parser import parse_command

# 1. Demo business owner
user, created = User.objects.get_or_create(username="ngozi", defaults={"email": "ngozi@swiftmartstores.ng"})
if created:
    user.set_password("ngozi12345")
    user.save()

business, _ = Business.objects.get_or_create(
    owner=user,
    defaults={
        "business_name": "SwiftMart Provisions & Electronics",
        "business_address": "Shop 14, Wuse Market, Abuja, FCT",
        "phone_number": "+234 803 555 1122",
        "email": "ngozi@swiftmartstores.ng",
        "default_currency": "NGN",
    },
)

# 2. Products commonly sold
product_data = [
    ("Bag of Rice (50kg)", "bag", 45000),
    ("Carton of Indomie", "carton", 4200),
    ("Carton of Coke (35cl)", "carton", 5800),
    ("Bag of Sugar (25kg)", "bag", 22000),
    ("Vegetable Oil (5L)", "unit", 9500),
    ("Bar Soap", "piece", 800),
    ("Powdered Milk (Tin)", "unit", 3200),
    ("Phone Charger", "piece", 2500),
    ("Extension Box (4-way)", "piece", 4500),
    ("LED Bulb (9W)", "piece", 1200),
]
for name, unit, price in product_data:
    Product.objects.get_or_create(
        business=business, name=name, defaults={"unit_price": price, "unit": unit}
    )

# 3. Simulate real voice/text commands going through the parser, exactly
#    as a shop owner would speak or type them.
commands = [
    ("TEXT", "Create invoice for Blessing Okafor, 2 bags of rice at 45000 naira each, due in 7 days"),
    ("VOICE", "Bill Tunde Adekunle for 3 cartons of indomie at 4200 each and 2 cartons of coke at 5800 each"),
    ("VOICE", "Invoice Funke Stores for 1 bag of sugar at 22000 naira each, due in 14 days"),
    ("TEXT", "New invoice for Emeka Obi, 5 pieces of soap at 800 naira each and 2 phone chargers at 2500 naira each, 10% discount"),
    ("VOICE", "Create invoice for Aisha Bello, 4 led bulbs at 1200 naira each"),
    ("TEXT", "Bill Chukwudi Eze for 2 vegetable oil at 9500 naira each and 3 powdered milk at 3200 naira each, due in 5 days"),
    ("VOICE", "Invoice Patricia Nwosu for 1 extension box at 4500 naira each and 6 led bulbs at 1200 naira each"),
    ("TEXT", "Create invoice for Ibrahim Sule, 3 bags of rice at 45000 naira each, 5% discount, due in 10 days"),
]

today = timezone.now().date()
created_invoices = []

for idx, (input_type, text) in enumerate(commands):
    parsed = parse_command(text)
    log = CommandLog.objects.create(
        business=business,
        user=user,
        input_type=input_type,
        raw_text=text,
        parsed_successfully=parsed.success,
        parsed_data=parsed.as_dict(),
        error_message="; ".join(parsed.errors) if parsed.errors else "",
    )
    if parsed.success:
        customer, _ = Customer.objects.get_or_create(business=business, name=parsed.customer_name)
        due_date = today + timedelta(days=parsed.due_in_days) if parsed.due_in_days else None
        invoice = Invoice.objects.create(
            business=business,
            customer=customer,
            due_date=due_date,
            source=input_type,
            raw_command_text=text,
            created_by=user,
        )
        for item in parsed.items:
            InvoiceItem.objects.create(
                invoice=invoice,
                description=item["description"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
        if parsed.discount_percent:
            invoice.discount = invoice.subtotal * (parsed.discount_percent / 100)

        # backdate a few invoices so the dashboard looks lived-in
        invoice.issue_date = today - timedelta(days=(len(commands) - idx) * 2)
        invoice.save()

        log.resulting_invoice = invoice
        log.save()
        created_invoices.append(invoice)

# 4. Add some payments to vary statuses (paid / partially paid / unpaid)
if len(created_invoices) >= 4:
    inv1 = created_invoices[0]
    Payment.objects.get_or_create(invoice=inv1, amount=inv1.total_amount, defaults={"method": "BANK_TRANSFER", "recorded_by": user})
    inv1.status = "PAID"
    inv1.save()

    inv2 = created_invoices[1]
    from decimal import Decimal
    half = inv2.total_amount / Decimal("2")
    Payment.objects.get_or_create(invoice=inv2, amount=half, defaults={"method": "CASH", "recorded_by": user})
    inv2.status = "PARTIALLY_PAID"
    inv2.save()

    inv3 = created_invoices[2]
    inv3.due_date = today - timedelta(days=3)
    inv3.status = "OVERDUE"
    inv3.save()

print(f"Seeded business: {business.business_name}")
print(f"Customers: {Customer.objects.filter(business=business).count()}")
print(f"Products: {Product.objects.filter(business=business).count()}")
print(f"Invoices: {Invoice.objects.filter(business=business).count()}")
print(f"Command logs: {CommandLog.objects.filter(business=business).count()}")
