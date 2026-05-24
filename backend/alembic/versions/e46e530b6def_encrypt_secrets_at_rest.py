"""encrypt_secrets_at_rest

Revision ID: e46e530b6def
Revises: 78f51ed407e1
Create Date: 2026-05-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e46e530b6def"
down_revision: Union[str, None] = "78f51ed407e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # api_keys: stop storing plaintext in key_hash; store ciphertext separately and keep a keyed hash for lookup.
    op.add_column("api_keys", sa.Column("ciphertext", sa.String(length=4096), nullable=True))
    op.add_column("api_keys", sa.Column("key_id", sa.String(length=50), nullable=False, server_default="v1"))
    op.add_column("api_keys", sa.Column("last4", sa.String(length=4), nullable=False, server_default=""))
    op.add_column("api_keys", sa.Column("rotated_at", sa.DateTime(), nullable=True))

    # email_accounts: rename *_encrypted -> *_ciphertext and add key_id/rotation.
    op.alter_column("email_accounts", "access_token_encrypted", new_column_name="access_token_ciphertext")
    op.alter_column("email_accounts", "refresh_token_encrypted", new_column_name="refresh_token_ciphertext")
    op.add_column(
        "email_accounts",
        sa.Column("access_token_key_id", sa.String(length=50), nullable=False, server_default="v1"),
    )
    op.add_column(
        "email_accounts",
        sa.Column("refresh_token_key_id", sa.String(length=50), nullable=True, server_default="v1"),
    )
    op.add_column("email_accounts", sa.Column("rotated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("email_accounts", "rotated_at")
    op.drop_column("email_accounts", "refresh_token_key_id")
    op.drop_column("email_accounts", "access_token_key_id")
    op.alter_column("email_accounts", "refresh_token_ciphertext", new_column_name="refresh_token_encrypted")
    op.alter_column("email_accounts", "access_token_ciphertext", new_column_name="access_token_encrypted")

    op.drop_column("api_keys", "rotated_at")
    op.drop_column("api_keys", "last4")
    op.drop_column("api_keys", "key_id")
    op.drop_column("api_keys", "ciphertext")
