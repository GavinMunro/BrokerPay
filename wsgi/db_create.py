__author__ = 'Miguel Grinberg'
from migrate.versioning import api

from brokerpay import db
from brokerpay import SQLALCHEMY_DATABASE_URI
from brokerpay import SQLALCHEMY_MIGRATE_REPO
from brokerpay import app  # Should contain cfg items above?

import os.path
db.create_all()
if not os.path.exists(SQLALCHEMY_MIGRATE_REPO):
    api.create(SQLALCHEMY_MIGRATE_REPO, 'database repo')
    api.version_contorl(SQLALCHEMY_DATABASE_URI, SQLALCHEMY_MIGRATE_REPO)
else:
    api.version_control(SQLALCHEMY_DATABASE_URI, SQLALCHEMY_MIGRATE_REPO,
                        api.version(SQLALCHEMY_MIGRATE_REPO))
