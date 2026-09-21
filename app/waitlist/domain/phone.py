import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType

from app.shared.domain.errors import ValidationFailed

_MOBILE_TYPES = {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}


def normalize_phone(raw: str, country_code: str) -> str:
    """Devuelve el celular en E.164 (+51987654321) o lanza ValidationFailed('invalid_phone').

    `country_code` es el ISO del local (PE, CL...). Acepta el número nacional o ya con prefijo.
    """
    error = ValidationFailed("invalid_phone", "Ingresa un celular válido.", field="phone")
    try:
        number = phonenumbers.parse(raw, country_code)
    except NumberParseException:
        raise error from None
    if not phonenumbers.is_valid_number(number) or phonenumbers.number_type(number) not in _MOBILE_TYPES:
        raise error
    if phonenumbers.region_code_for_number(number) != country_code:
        raise error
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def display_phone(e164: str) -> str:
    """+51987654321 -> +51 987 654 321"""
    return phonenumbers.format_number(phonenumbers.parse(e164), phonenumbers.PhoneNumberFormat.INTERNATIONAL)
