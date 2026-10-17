"""Class home room: the room a class keeps unless a lesson needs its own room.

Adds ``class.home_room_id`` as a nullable reference to ``room``. The composite
key keeps the room in the class's school; a null value means Automática. No
cascade: removing a room clears the column in the same transaction.

Revision ID: 0007_class_home_room
Revises: 0006_room_types
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_class_home_room"
down_revision = "0006_room_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("class", sa.Column("home_room_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_class_home_room_org",
        "class",
        "room",
        ["organization_id", "home_room_id"],
        ["organization_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_class_home_room_org", "class", type_="foreignkey")
    op.drop_column("class", "home_room_id")
