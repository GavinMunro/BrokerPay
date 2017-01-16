from setuptools import setup

setup(name='BrokerPay',
      version='1.0',
      description='Broker payment claims app',
      author='Gavin Munro',
      author_email='Gavin.Munro@careersaustralia.edu.au',
      url='http://www.python.org/sigs/distutils-sig/',
     install_requires=[
         'MarkupSafe',
         'Flask',
         'Flask-SQLAlchemy',
         'Flask-Login',
         'Flask-Uploads',
         'SQLAlchemy-Migrate',
         'simple-salesforce',
         'fdfgen',
         'PyPDF2'
     ],
)