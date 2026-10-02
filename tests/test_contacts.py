from io import BytesIO

from app import extract_contact_names, personalize_text


def test_contact_columns_override_email_guess():
    rows = [
        ["Email Address", "Title", "First Name", "Lastname"],
        ["jane99@example.com", "Dr.", "Jane", "Doe"],
    ]

    assert extract_contact_names(rows) == {
        "jane99@example.com": "Dr. Jane Doe",
    }
    assert personalize_text(
        "{{name}}|{{first_name}}|{{last_name}}",
        "jane99@example.com",
        "Dr. Jane Doe",
    ) == "Dr. Jane Doe|Jane|Doe"


def test_legacy_xls_uses_xlrd(authenticated_client, monkeypatch):
    class Sheet:
        nrows = 2
        ncols = 4
        values = [
            ["Email", "Title", "First Name", "Last Name"],
            ["jane@example.com", "Ms.", "Jane", "Doe"],
        ]

        def cell_value(self, row, column):
            return self.values[row][column]

    class Workbook:
        def sheets(self):
            return [Sheet()]

    import xlrd
    monkeypatch.setattr(xlrd, "open_workbook", lambda **_: Workbook())

    response = authenticated_client.post(
        "/extract",
        data={"file": (BytesIO(b"legacy-xls"), "contacts.xls")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["names"]["jane@example.com"] == "Ms. Jane Doe"
