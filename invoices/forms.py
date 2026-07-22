from django import forms
from django.contrib.auth.models import User
from .models import Business, Customer, Product, Invoice, Payment


class SignUpForm(forms.Form):
    business_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username


class CommandInputForm(forms.Form):
    command_text = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "e.g. Create invoice for John Doe, 2 bags of rice at 15000 naira each, due in 7 days",
        }),
        label="Describe the invoice (type or use the microphone)",
    )
    input_type = forms.ChoiceField(
        choices=[("TEXT", "Text"), ("VOICE", "Voice")], initial="TEXT", widget=forms.HiddenInput
    )


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone_number", "email", "address"]


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "description", "unit_price", "unit", "is_active"]


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "reference", "payment_date"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
        }


class InvoiceStatusForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["status", "due_date", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
