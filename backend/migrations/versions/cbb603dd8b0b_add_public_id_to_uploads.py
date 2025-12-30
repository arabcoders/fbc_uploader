"""add_public_id_to_uploads

Revision ID: cbb603dd8b0b
Revises: 5dc14b681055
Create Date: 2025-12-30 17:50:45.019140
"""
from alembic import op
import sqlalchemy as sa
import secrets


# revision identifiers, used by Alembic.
revision = 'cbb603dd8b0b'
down_revision = '5dc14b681055'
branch_labels = None
depends_on = None


def upgrade():
    # Add public_id column as nullable first
    op.add_column('uploads', sa.Column('public_id', sa.String(length=64), nullable=True))
    
    # Populate existing rows with random public_ids
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id FROM uploads"))
    for row in result:
        public_id = secrets.token_urlsafe(18)
        connection.execute(
            sa.text("UPDATE uploads SET public_id = :public_id WHERE id = :id"),
            {"public_id": public_id, "id": row[0]}
        )
    
    # For SQLite, we need to use batch operations to make column non-nullable
    with op.batch_alter_table('uploads', schema=None) as batch_op:
        batch_op.alter_column('public_id', nullable=False)
        batch_op.create_unique_constraint('uq_uploads_public_id', ['public_id'])
        batch_op.create_index('ix_uploads_public_id', ['public_id'])


def downgrade():
    with op.batch_alter_table('uploads', schema=None) as batch_op:
        batch_op.drop_index('ix_uploads_public_id')
        batch_op.drop_constraint('uq_uploads_public_id', type_='unique')
        batch_op.drop_column('public_id')

