from django.contrib import admin
from .models import Business, Customer, Product, Invoice, InvoiceItem, Payment, CommandLog


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "status", "source", "issue_date", "total_amount")
    list_filter = ("status", "source")
    search_fields = ("invoice_number", "customer__name")
    inlines = [InvoiceItemInline, PaymentInline]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "phone_number", "email")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "unit_price", "unit", "is_active")


@admin.register(CommandLog)
class CommandLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "input_type", "parsed_successfully", "raw_text")
    list_filter = ("input_type", "parsed_successfully")


admin.site.register(Business)
admin.site.register(Payment)
