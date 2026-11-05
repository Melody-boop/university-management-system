from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.forms import modelform_factory

from .models import AdmissionApplication, Payment, Student


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))


class AdmissionForm(forms.ModelForm):
    class Meta:
        model = AdmissionApplication
        fields = ["first_name", "last_name", "email", "phone", "programme", "qualification", "document"]
        widgets = {"document": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"})}

    def clean_document(self):
        document = self.cleaned_data.get("document")
        if document:
            allowed = {"application/pdf", "image/jpeg", "image/png"}
            if document.content_type not in allowed or document.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Upload a PDF, JPG, or PNG file smaller than 5 MB.")
        return document


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["fee", "amount", "method", "reference"]


def record_form(model, exclude=()):
    fields = [field.name for field in model._meta.fields if field.editable and field.name not in {"id", "created_at", "updated_at", "registered_at", "submitted_at", "paid_at", "date_joined", "last_login"}]
    fields.extend(field.name for field in model._meta.many_to_many if field.editable)
    return modelform_factory(model, fields=fields, exclude=exclude)


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["phone", "postal_address", "county"]