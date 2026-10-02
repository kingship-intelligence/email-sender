import json

from app import app, db, make_unsubscribe_token
from models import Campaign, CampaignRecipient, DailySendUsage, Suppression


def test_get_does_not_unsubscribe_but_post_is_idempotent(client, user):
    with app.app_context():
        token = make_unsubscribe_token(user, "person@example.com")

    response = client.get(f"/unsubscribe/{token}")
    assert response.status_code == 200
    with app.app_context():
        assert Suppression.query.count() == 0

    assert client.post(f"/unsubscribe/{token}").status_code == 200
    assert client.post(f"/unsubscribe/{token}").status_code == 200
    with app.app_context():
        assert Suppression.query.count() == 1


def test_tampered_token_is_rejected(client, user):
    with app.app_context():
        token = make_unsubscribe_token(user, "person@example.com")

    response = client.post(f"/unsubscribe/{token}tampered")
    assert response.status_code == 400
    with app.app_context():
        assert db.session.query(Suppression).count() == 0


def test_suppressed_recipient_does_not_consume_quota(authenticated_client, user):
    with app.app_context():
        db.session.add(Suppression(
            user_id=user,
            email="person@example.com",
            source="unsubscribe",
        ))
        db.session.commit()

    response = authenticated_client.post(
        "/send-bulk",
        data={
            "emails": json.dumps(["person@example.com"]),
            "names": "{}",
            "subject": "Hello",
            "body": "<p>Body</p>",
            "name": "Suppressed test",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["suppressed_count"] == 1
    with app.app_context():
        assert CampaignRecipient.query.one().status == "suppressed"
        assert DailySendUsage.query.one().attempt_count == 0


def test_suppressed_status_is_not_counted_as_failure(authenticated_client, user):
    with app.app_context():
        campaign = Campaign(
            user_id=user,
            name="Metrics",
            subject="Hello",
            body="<p>Body</p>",
            status="completed",
            total=1,
        )
        db.session.add(campaign)
        db.session.flush()
        db.session.add(CampaignRecipient(
            campaign_id=campaign.id,
            email="person@example.com",
            status="suppressed",
        ))
        db.session.commit()
        campaign_id = campaign.id

    status = authenticated_client.get(f"/campaign/{campaign_id}/status").get_json()
    assert status["suppressed"] == 1
    assert status["failed"] == 0
    assert status["failure_rate"] is None
