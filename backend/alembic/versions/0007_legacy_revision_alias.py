"""Recognize the legacy pre-RGPD head in the current migration graph."""

revision = "0007_qualify_user_rls_policy"
down_revision = "0006_non_mutating_ensure_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy revision already applied the user RLS policy. Its descendant
    # performs the compatibility repair before the legal-acceptance migration.
    pass


def downgrade() -> None:
    pass
