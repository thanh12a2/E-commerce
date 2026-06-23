from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(label="Staff username", max_length=150)
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)


class StaffRegisterForm(forms.Form):
    username = forms.CharField(label="Username", max_length=150)
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirm_password"):
            raise forms.ValidationError("Password confirmation does not match.")
        return cleaned_data


class _BaseItemMutationForm(forms.Form):
    service = forms.ChoiceField(label="Category", choices=[])
    name = forms.CharField(max_length=255)
    brand = forms.CharField(max_length=120)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    image_url = forms.URLField(required=False)
    price = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    stock = forms.IntegerField(min_value=0)

    def __init__(self, *args, **kwargs):
        service_choices = kwargs.pop("service_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["service"].choices = service_choices


class CreateItemForm(_BaseItemMutationForm):
    pass


class UpdateItemForm(_BaseItemMutationForm):
    product_id = forms.IntegerField(min_value=1)


class DeleteItemForm(forms.Form):
    service = forms.ChoiceField(label="Category", choices=[])
    product_id = forms.IntegerField(min_value=1)

    def __init__(self, *args, **kwargs):
        service_choices = kwargs.pop("service_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["service"].choices = service_choices


class CustomerEditForm(forms.Form):
    username = forms.CharField(label="Username", max_length=150)
    email = forms.EmailField(label="Email")
    first_name = forms.CharField(label="First name", max_length=150, required=False)
    last_name = forms.CharField(label="Last name", max_length=150, required=False)

    def __init__(self, *args, **kwargs):
        self._instance_user = kwargs.pop("instance_user", None)
        super().__init__(*args, **kwargs)
