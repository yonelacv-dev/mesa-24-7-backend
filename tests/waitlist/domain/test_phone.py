import pytest

from app.shared.domain.errors import ValidationFailed
from app.waitlist.domain.phone import display_phone, normalize_phone


@pytest.mark.parametrize("raw", ["987 654 321", "987654321", "+51 987 654 321", "+51987654321", "(987) 654-321"])
def test_peru_mobile_is_normalized_to_e164(raw):
    assert normalize_phone(raw, "PE") == "+51987654321"


@pytest.mark.parametrize("raw", ["9 8765 4321", "987654321", "+56 9 8765 4321"])
def test_chile_mobile_is_normalized_to_e164(raw):
    assert normalize_phone(raw, "CL") == "+56987654321"


@pytest.mark.parametrize("raw", ["", "abc", "12345", "98765432", "9876543210", "887654321"])
def test_invalid_peru_numbers_are_rejected(raw):
    with pytest.raises(ValidationFailed) as error:
        normalize_phone(raw, "PE")
    assert error.value.code == "invalid_phone"
    assert error.value.field == "phone"


def test_number_from_another_country_is_rejected():
    with pytest.raises(ValidationFailed):
        normalize_phone("+56 9 8765 4321", "PE")


def test_display_phone_is_grouped():
    assert display_phone("+51987654321") == "+51 987 654 321"
