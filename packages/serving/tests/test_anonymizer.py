"""Unit tests for PII and secret anonymizer."""

from nexcoder_serving.raft.anonymizer import Anonymizer


def test_anonymize_email_and_cpf() -> None:
    anonymizer = Anonymizer()
    text = "User contact is developer@example.org with tax ID 123.456.789-01."
    anonymized = anonymizer.anonymize_text(text)

    assert "developer@example.org" not in anonymized
    assert "123.456.789-01" not in anonymized
    assert "[EMAIL_1]" in anonymized
    assert "[CPF_1]" in anonymized

    # Deanonymization
    restored = anonymizer.deanonymize_text(anonymized)
    assert restored == text


def test_anonymize_cnpj_and_phone() -> None:
    anonymizer = Anonymizer()
    text = "Company CNPJ is 12.345.678/0001-99 and customer support is (11) 98765-4321."
    anonymized = anonymizer.anonymize_text(text)

    assert "12.345.678/0001-99" not in anonymized
    assert "(11) 98765-4321" not in anonymized
    assert "[CNPJ_1]" in anonymized
    assert "[PHONE_1]" in anonymized


def test_anonymize_record_nested() -> None:
    anonymizer = Anonymizer()
    data = {
        "user": "Alice",
        "email": "alice@example.com",
        "metadata": {
            "backup_email": "alice_backup@example.com",
            "ip": "192.168.1.50",
        },
        "tags": ["admin", "support@company.com"],
    }
    result = anonymizer.anonymize_record(data)

    assert "[EMAIL_1]" in result["email"]
    assert "[EMAIL_2]" in result["metadata"]["backup_email"]
    assert "[IP_1]" in result["metadata"]["ip"]
    assert "[EMAIL_3]" in result["tags"][1]
