import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import normalize as norm


def test_phone_normalization_variants_converge():
    assert norm.normalize_phone("9876543210") == "+919876543210"
    assert norm.normalize_phone("+91 98765 12345") == "+919876512345"
    assert norm.normalize_phone("098-765-12345") == "+919876512345"


def test_phone_missing_returns_none():
    assert norm.normalize_phone("") is None
    assert norm.normalize_phone(None) is None


def test_date_variants_converge():
    assert norm.normalize_date("2021-06") == ("2021-06", "month")
    assert norm.normalize_date("Jun 2021")[0] == "2021-06"
    assert norm.normalize_date("06/2021")[0] == "2021-06"
    assert norm.normalize_date("2018")[0] == "2018"
    assert norm.normalize_date("2018")[1] == "year"


def test_skill_canonicalization():
    assert norm.normalize_skill("Node.js") == "Node.js"
    assert norm.normalize_skill("NodeJS") == "Node.js"
    assert norm.normalize_skill("Go") == "Go"
    assert norm.normalize_skill("Golang") == "Go"


def test_name_and_email_cleanup():
    assert norm.normalize_name("  ananya   sharma ") == "Ananya Sharma"
    assert norm.normalize_email("  Ananya.Sharma@GMAIL.com ") == "ananya.sharma@gmail.com"


if __name__ == "__main__":
    test_phone_normalization_variants_converge()
    test_phone_missing_returns_none()
    test_date_variants_converge()
    test_skill_canonicalization()
    test_name_and_email_cleanup()
    print("All normalize tests passed.")
