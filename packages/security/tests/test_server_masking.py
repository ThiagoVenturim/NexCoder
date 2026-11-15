"""Unit tests for PII and sensitive data masking across logs and dumps."""


from nexcoder_security.server.masking import DataMasker


def test_mask_synthetic_pii_text():
    masker = DataMasker.basic()

    synthetic_text = (
        "User contact: alice@corp.example.com, CPF 123.456.789-00, CNPJ 12.345.678/0001-90, "
        "Phone (11) 98765-4321, Card 4111 2222 3333 4444, IP 192.168.1.105, "
        "Secret sk-live9876543210abcdef, URI postgres://dbuser:supersecretpass@127.0.0.1:5432/app"
    )

    masked = masker.mask_text(synthetic_text)

    # Verify all synthetic PII is removed
    assert "alice@corp.example.com" not in masked
    assert "123.456.789-00" not in masked
    assert "12.345.678/0001-90" not in masked
    assert "(11) 98765-4321" not in masked
    assert "4111 2222 3333 4444" not in masked
    assert "192.168.1.105" not in masked
    assert "sk-live9876543210abcdef" not in masked
    assert "supersecretpass" not in masked

    # Verify placeholders are present
    assert "[EMAIL_1]" in masked
    assert "[CPF_1]" in masked
    assert "[CNPJ_1]" in masked
    assert "[PHONE_1]" in masked
    assert "[CARD_1]" in masked
    assert "[IP_1]" in masked
    assert "[SECRET_1]" in masked
    assert "[PASSWORD_1]" in masked

    # Verify unmask restores original text
    restored = masker.unmask_text(masked)
    assert restored == synthetic_text


def test_mask_log_file():
    masker = DataMasker.basic()

    log_content = (
        "2026-11-15 12:00:01 INFO [auth] User login attempt for bob@example.com from 10.0.0.5\n"
        "2026-11-15 12:00:02 WARN [api] Invalid token Bearer sk-antigravity-secret-key-123\n"
    )

    masked_log = masker.mask_log_file(log_content)
    assert "bob@example.com" not in masked_log
    assert "10.0.0.5" not in masked_log
    assert "sk-antigravity-secret-key-123" not in masked_log
    assert "[EMAIL_1]" in masked_log
    assert "[IP_1]" in masked_log
    assert "[SECRET_1]" in masked_log


def test_mask_json_logs_and_records():
    masker = DataMasker.basic()

    record = {
        "user_id": 42,
        "email": "carol@example.org",
        "cpf": "999.888.777-66",
        "auth": {
            "password": "ClearTextPassword123",
            "api_key": "sk-secret-key-abcdef",
        },
        "metadata": ["note with phone +55 11 91234-5678", "normal text"],
    }

    masked_record = masker.mask_record(record)
    assert masked_record["email"] == "[EMAIL_1]"
    assert masked_record["cpf"] == "[CPF_1]"
    assert masked_record["auth"]["password"] == "[SECRET_1]"
    assert masked_record["auth"]["api_key"] == "[SECRET_2]"
    assert "+55 11 91234-5678" not in masked_record["metadata"][0]
    assert "[PHONE_1]" in masked_record["metadata"][0]


def test_mask_sql_dump():
    masker = DataMasker.basic()

    sql_dump = """-- PostgreSQL database dump
CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(255), cpf VARCHAR(14), notes TEXT);
INSERT INTO users (id, email, cpf, notes) VALUES (1, 'dan@company.com', '111.222.333-44', 'Contact at 10.1.2.3');
INSERT INTO users (id, email, cpf, notes) VALUES (2, 'eva@corp.org', '555.666.777-88', 'Secret token sk-mytoken123456');
"""

    masked_sql = masker.mask_sql_dump(sql_dump)

    assert "dan@company.com" not in masked_sql
    assert "eva@corp.org" not in masked_sql
    assert "111.222.333-44" not in masked_sql
    assert "555.666.777-88" not in masked_sql
    assert "sk-mytoken123456" not in masked_sql

    # SQL syntax remains intact
    assert "CREATE TABLE users" in masked_sql
    expected_row = "INSERT INTO users (id, email, cpf, notes) VALUES (1, '[EMAIL_1]', '[CPF_1]', 'Contact at [IP_1]');"
    assert expected_row in masked_sql


def test_mask_csv():
    masker = DataMasker.basic()

    csv_data = "id,name,email,cpf\n1,Developer,dev@test.com,333.444.555-66\n2,Tester,qa@test.com,777.888.999-00"
    masked_csv = masker.mask_csv(csv_data)

    assert "dev@test.com" not in masked_csv
    assert "qa@test.com" not in masked_csv
    assert "333.444.555-66" not in masked_csv
    assert "[EMAIL_1]" in masked_csv
    assert "[CPF_1]" in masked_csv


def test_masking_advanced_salted_hash():
    masker = DataMasker.advanced(salt="test-salt-123", strategy="hash")

    text = "Contact user@example.com with key sk-securekey12345"
    masked = masker.mask_text(text)

    assert "user@example.com" not in masked
    assert "sk-securekey12345" not in masked
    assert "[EMAIL_" in masked
    assert "[SECRET_" in masked
    # Hash digest format
    assert len(masked) > 0
