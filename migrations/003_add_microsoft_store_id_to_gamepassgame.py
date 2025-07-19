from data.models import GamePassGame, db


def migrate():
    # migrator = db.migrator
    # with db.atomic():
    #     migrator.add_column(GamePassGame, 'microsoft_store_id', CharField(null=True, unique=True)).run()
    pass

def rollback():
    migrator = db.migrator
    with db.atomic():
        migrator.drop_column(GamePassGame, 'microsoft_store_id').run()
