"""Tests for the AccountInfo model in models/account.py."""

from dominionsc.models.account import AccountInfo


def test_account_info_default_measurement_types_is_empty_list():
    """AccountInfo.measurement_types defaults to an empty list."""
    account = AccountInfo()

    assert account.measurement_types == []


def test_account_info_default_service_address_is_empty_string():
    """AccountInfo.service_address_and_account_no defaults to an empty string."""
    account = AccountInfo()

    assert account.service_address_and_account_no == ""


def test_account_info_to_legacy_list_structure():
    """to_legacy_list returns [measurement_types, service_address_and_account_no]."""
    account = AccountInfo(measurement_types=["ELECTRIC"], service_address_and_account_no="123 MAIN ST")

    result = account.to_legacy_list()

    assert result == [["ELECTRIC"], "123 MAIN ST"]


def test_account_info_to_legacy_list_first_element_is_measurement_types():
    """The first element of to_legacy_list is the measurement_types list itself (same object)."""
    account = AccountInfo(measurement_types=["ELECTRIC", "GAS"])

    result = account.to_legacy_list()

    assert result[0] is account.measurement_types


def test_account_info_to_legacy_list_second_element_is_service_address():
    """The second element of to_legacy_list is the service_address_and_account_no string."""
    account = AccountInfo(service_address_and_account_no="456 OAK AVE (*-****-****1-2345)")

    result = account.to_legacy_list()

    assert result[1] == "456 OAK AVE (*-****-****1-2345)"


def test_account_info_default_instances_do_not_share_measurement_types():
    """Each AccountInfo instance gets its own measurement_types list via field(default_factory)."""
    first = AccountInfo()
    second = AccountInfo()

    first.measurement_types.append("ELECTRIC")

    assert second.measurement_types == []
