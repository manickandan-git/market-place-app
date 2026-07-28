import pytest

from app.exceptions import StaleVersionError
from app.services import UserService


def test_matching_version_is_accepted() -> None:
    UserService._check_version(2, 2)


def test_stale_version_is_rejected() -> None:
    with pytest.raises(StaleVersionError):
        UserService._check_version(3, 2)
