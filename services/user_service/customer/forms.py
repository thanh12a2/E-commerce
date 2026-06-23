from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm


User = get_user_model()


class CustomerLoginForm(AuthenticationForm):
    username = forms.CharField(label="Username", max_length=150)
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)


class CustomerRegisterForm(forms.Form):
    username = forms.CharField(label="Username", max_length=150)
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="Confirm Password", strip=False, widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
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


class ProductFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=120)
    category = forms.ChoiceField(required=False, choices=[("all", "All")], initial="all")
    stock = forms.ChoiceField(
        required=False,
        choices=[("all", "All"), ("in_stock", "In stock")],
        initial="all",
    )
    price_range = forms.ChoiceField(
        required=False,
        choices=[
            ("all", "Any price"),
            ("under_500", "Under 500"),
            ("500_1000", "500 - 1000"),
            ("1000_2000", "1000 - 2000"),
            ("above_2000", "Above 2000"),
        ],
        initial="all",
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("newest", "Newest"),
            ("price_low_high", "Price: low to high"),
            ("price_high_low", "Price: high to low"),
            ("name_az", "Name A-Z"),
            ("name_za", "Name Z-A"),
        ],
        initial="newest",
    )
    brand = forms.ChoiceField(required=False, choices=[("all", "All brands")], initial="all")

    def __init__(self, *args, **kwargs):
        brand_choices = kwargs.pop("brand_choices", None)
        category_choices = kwargs.pop("category_choices", None)
        super().__init__(*args, **kwargs)

        if category_choices:
            self.fields["category"].choices = [("all", "All categories"), *category_choices]

        if brand_choices:
            self.fields["brand"].choices = [("all", "All brands"), *((brand, brand) for brand in brand_choices)]

        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Search product name, brand, or category...",
                "class": "product-field-input",
            }
        )
        for field_name in ["category", "stock", "price_range", "sort", "brand"]:
            existing = self.fields[field_name].widget.attrs.get("class", "")
            self.fields[field_name].widget.attrs["class"] = f"{existing} product-field-select".strip()
