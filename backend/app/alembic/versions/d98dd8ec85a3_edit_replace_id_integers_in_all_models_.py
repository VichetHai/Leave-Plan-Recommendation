"""Edit replace id integers in all models to use UUID instead

Revision ID: d98dd8ec85a3
Revises: 9c0a54914c78
Create Date: 2024-07-19 04:08:04.000976

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd98dd8ec85a3'
down_revision = '9c0a54914c78'
branch_labels = None
depends_on = None


def upgrade():
    # Add new UUID columns (RAW(16) on Oracle, handled by sa.Uuid)
    op.add_column('user', sa.Column('new_id', sa.Uuid(), nullable=True))
    op.add_column('item', sa.Column('new_id', sa.Uuid(), nullable=True))
    op.add_column('item', sa.Column('new_owner_id', sa.Uuid(), nullable=True))

    # Populate new UUID columns (RAWTOHEX converts SYS_GUID RAW(16) to CHAR(32))
    op.execute('UPDATE "user" SET new_id = RAWTOHEX(SYS_GUID())')
    op.execute('UPDATE item SET new_id = RAWTOHEX(SYS_GUID())')
    op.execute('UPDATE item SET new_owner_id = (SELECT new_id FROM "user" WHERE "user".id = item.owner_id)')

    # Set not nullable
    op.alter_column('user', 'new_id', nullable=False)
    op.alter_column('item', 'new_id', nullable=False)

    # Drop old FK, columns, rename new columns
    op.drop_constraint('item_owner_id_fkey', 'item', type_='foreignkey')
    op.drop_column('item', 'owner_id')
    op.alter_column('item', 'new_owner_id', new_column_name='owner_id')

    op.drop_column('user', 'id')
    op.alter_column('user', 'new_id', new_column_name='id')

    op.drop_column('item', 'id')
    op.alter_column('item', 'new_id', new_column_name='id')

    # Recreate primary keys and foreign key
    op.create_primary_key('user_pkey', 'user', ['id'])
    op.create_primary_key('item_pkey', 'item', ['id'])
    op.create_foreign_key('item_owner_id_fkey', 'item', 'user', ['owner_id'], ['id'])


def downgrade():
    op.add_column('user', sa.Column('old_id', sa.Integer(), autoincrement=True, nullable=True))
    op.add_column('item', sa.Column('old_id', sa.Integer(), autoincrement=True, nullable=True))
    op.add_column('item', sa.Column('old_owner_id', sa.Integer(), nullable=True))

    # Oracle sequence syntax
    op.execute('CREATE SEQUENCE user_id_seq START WITH 1 INCREMENT BY 1')
    op.execute('CREATE SEQUENCE item_id_seq START WITH 1 INCREMENT BY 1')

    op.execute('UPDATE "user" SET old_id = user_id_seq.NEXTVAL')
    op.execute('UPDATE item SET old_id = item_id_seq.NEXTVAL')
    op.execute('UPDATE item SET old_owner_id = (SELECT old_id FROM "user" WHERE "user".id = item.owner_id)')

    op.drop_constraint('item_owner_id_fkey', 'item', type_='foreignkey')
    op.drop_column('item', 'owner_id')
    op.alter_column('item', 'old_owner_id', new_column_name='owner_id')

    op.drop_column('user', 'id')
    op.alter_column('user', 'old_id', new_column_name='id')

    op.drop_column('item', 'id')
    op.alter_column('item', 'old_id', new_column_name='id')

    op.create_primary_key('user_pkey', 'user', ['id'])
    op.create_primary_key('item_pkey', 'item', ['id'])
    op.create_foreign_key('item_owner_id_fkey', 'item', 'user', ['owner_id'], ['id'])

    op.execute('DROP SEQUENCE user_id_seq')
    op.execute('DROP SEQUENCE item_id_seq')
