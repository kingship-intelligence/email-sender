"""Production safety baseline for fresh and existing databases."""

from alembic import op
import sqlalchemy as sa

revision = "0001_production_safety"
down_revision = None
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    tables = _tables()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("plan", sa.String(20), nullable=True),
            sa.Column("stripe_customer_id", sa.String(255), nullable=True),
            sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
            sa.Column("smtp_host", sa.String(255), nullable=True),
            sa.Column("smtp_port", sa.Integer(), nullable=True),
            sa.Column("smtp_user", sa.String(255), nullable=True),
            sa.Column("smtp_pass_enc", sa.Text(), nullable=True),
            sa.Column("smtp_use_tls", sa.Boolean(), nullable=True),
            sa.Column("smtp_from", sa.String(255), nullable=True),
            sa.Column("smtp_sender_name", sa.String(255), nullable=True),
            sa.Column("smtp_reply_to", sa.String(255), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    else:
        columns = _columns("users")
        additions = (
            ("verified", sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true())),
            ("smtp_sender_name", sa.Column("smtp_sender_name", sa.String(255))),
            ("smtp_reply_to", sa.Column("smtp_reply_to", sa.String(255))),
        )
        for name, column in additions:
            if name not in columns:
                op.add_column("users", column)

    tables = _tables()
    if "campaigns" not in tables:
        op.create_table(
            "campaigns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(255)),
            sa.Column("subject", sa.String(500)),
            sa.Column("body", sa.Text()),
            sa.Column("status", sa.String(20)),
            sa.Column("total", sa.Integer()),
            sa.Column("sent_ok", sa.Integer()),
            sa.Column("sent_fail", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
        )

    if "campaign_recipients" not in tables:
        op.create_table(
            "campaign_recipients",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255)),
            sa.Column("status", sa.String(20)),
            sa.Column("error", sa.Text()),
            sa.Column("sent_at", sa.DateTime()),
        )
    elif "name" not in _columns("campaign_recipients"):
        op.add_column("campaign_recipients", sa.Column("name", sa.String(255)))

    if "scheduled_campaigns" not in tables:
        op.create_table(
            "scheduled_campaigns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(500), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("emails_json", sa.Text(), nullable=False),
            sa.Column("names_json", sa.Text()),
            sa.Column("next_run_at", sa.DateTime(), nullable=False),
            sa.Column("last_run_at", sa.DateTime()),
            sa.Column("active", sa.Boolean()),
            sa.Column("frequency", sa.String(20), nullable=False, server_default="weekly"),
            sa.Column("created_at", sa.DateTime()),
        )
    else:
        columns = _columns("scheduled_campaigns")
        if "frequency" not in columns:
            op.add_column(
                "scheduled_campaigns",
                sa.Column("frequency", sa.String(20), nullable=False, server_default="weekly"),
            )
        if "names_json" not in columns:
            op.add_column("scheduled_campaigns", sa.Column("names_json", sa.Text()))

    if "daily_send_usage" not in tables:
        op.create_table(
            "daily_send_usage",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("usage_date", sa.Date(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("user_id", "usage_date", name="uq_daily_send_usage_user_date"),
        )

    if "suppressions" not in tables:
        op.create_table(
            "suppressions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("source", sa.String(50), nullable=False, server_default="unsubscribe"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "email", name="uq_suppressions_user_email"),
        )
        op.create_index(
            "ix_suppressions_user_email",
            "suppressions",
            ["user_id", "email"],
        )

    if "sessions" not in tables:
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.String(255), unique=True),
            sa.Column("data", sa.LargeBinary()),
            sa.Column("expiry", sa.DateTime()),
        )


def downgrade():
    # This revision adopts pre-existing production tables, so destructive
    # downgrade is intentionally unsupported.
    pass
