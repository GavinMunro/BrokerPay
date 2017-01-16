import os
from flask import Flask
from flask import request, url_for, redirect, render_template, flash, session, abort, g
# What's g? It's some thread local context session global. Should really use session I think.
from flask import get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import select, exists, subquery, text, and_     # For raw SQL usage
from sqlalchemy import func, distinct, desc
from sqlalchemy.orm.session import make_transient
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import Enum

#from SQLAlchemy.orm import aliased
from flask.ext.login import LoginManager, login_user, logout_user, current_user, login_required
from werkzeug.utils import secure_filename

from datetime import datetime

from simple_salesforce import Salesforce
from flask import send_from_directory  # For serving uploaded files
import csv  # For parsing uploaded claims
from fdfgen import forge_fdf
from sys import path
from itertools import ifilter, ifilterfalse, imap

# Base config
app = Flask(__name__)
app.secret_key = 'Quick! To the cloud!'  # app arrently secret key is reqd for flash msgs to work
app.config.from_pyfile('brokerpay.cfg')
app.config['PROPAGATE_EXCEPTIONS'] = True
# The app.config dict should go in the brokerpay.cfg file
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Max upload size 2MB
# app.config['UPLOAD_FOLDER'] = os.environ['OPENSHIFT_TMP_DIR']  # Goes to /tmp/
app.config['UPLOAD_FOLDER'] = os.environ['OPENSHIFT_TMP_DIR']  # for dbg purposes ['OPENSHIFT_DATA_DIR']
#app.config['PGDATESTYLE'] = 'ISO, DMY'       # This string format for datestyle cmd needed to prevent MDY dates!
app.config['OPENSHIFT_POSTGRESQL_DATESTYLE'] = 'ISO, DMY'
app.config['OPENSHIFT_POSTGRESQL_LOCALE'] = 'en_AU'
# The configs above should perhaps go in the .cfg file

db = SQLAlchemy(app)  # Let there be data!

# Setup Flask Login extension
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(usr_id):
    return User.query.get_or_404(usr_id)  # Needs to return None if id not valid


# ######################################################
# Setup the data model with SQL Alchemy defined classes
# ######################################################

class Broker(db.Model):
    __tablename__ = 'broker'
    id = db.Column('broker_id', db.Integer, primary_key=True)
    orgname = db.Column('orgname', db.String(60), nullable=False)
    address = db.Column('address', db.Text(200), nullable=False)
    suburb = db.Column('suburb', db.String(50), nullable=False)
    state = db.Column('state', db.String(3), nullable=False)
    postcode = db.Column('postcode', db.String(4), nullable=False)
    abn = db.Column('abn', db.String(14), nullable=False)
    # These fields are mandatory for invoicing purposes
    users = db.relationship('User', lazy='dynamic')  # SQLA one-to-many with User
    # # Will we have only one MOU at any time for a given broker? May need to check older ones.
    # mous = db.relationship('MOU', lazy='dynamic', secondary='agreed',
    #                        primaryjoin="MOU.id == agreed.c.mou_id",
    #                        secondaryjoin="Broker.id == agreed.c.mou_id"
    #                        )
    # # I find SQLA's term "backref" a bit confusing but all this join stuff for a many-to-many? Geez.
    '''
    # http://stackoverflow.com/questions/22110515/flask-help-understanding-primaryjoin-secondaryjoin-on-a-many-to-many-relationshi
    # If your model has all required ForeignKeys specified, sqlachemy is smart enough to figure out
    # the parameters for primaryjoin and secondaryjoin itself. So this should work just fine:
    # eg. favourites_table is a m-to-m between User and Listing
    favorites  = db.relationship('Listing',
        secondary = favorites_table,',
        backref = db.backref('users', lazy = 'dynamic'),
        lazy = 'dynamic',
        )
    '''
    mou_list = db.relationship('MOU', secondary='agreed',
                               backref=db.backref('broker',
                                                  lazy='dynamic'),
                               lazy='dynamic')  # Voila! A many-to-many relation in one statement.

    def __init__(self, name, abn):
        self.orgname = name
        self.abn = abn


agreed = db.Table('agreed',
                  db.Column('broker_id', db.ForeignKey('broker.broker_id'), primary_key=True),
                  db.Column('mou_id',  db.ForeignKey('mou.mou_id'), primary_key=True)
                  )  # This is an "association table" - SA's cumbersome way of doing many-to-many


class RefSrc(db.Model):
    __tablename__ = 'ref_src'
    alt_name = db.Column('name', db.String(40), primary_key=True)
    broker = db.Column('broker', db.Integer, db.ForeignKey('broker.broker_id'))

    def __init__(self, broker, alt_name):
        self.alt_name = alt_name
        self.broker = broker


# Below is the definitions of various enums used in the database. These are tuples initially in Python.
# Then for use as an Enum in Postgress, eg.: "db.Column('stage', db.Enum(*stage_enum, name='stage_enum'))"

delivery_enum = ('Classroom Based', 'Online', 'Flex-Learn')
# Note: might have 'Campus' and 'Electronic Based' and 'Flex' also.


mou_styles = ('pct_stage', 'pct_gross', 'flat_fee')

course_types = ('Cert', 'Dip', 'Dbl', 'Nursing', 'Dip of Logistics', 'Dip of Counselling', 'Dbl Dip C&CSW',
                'Triple Dip Bus Mgt, HR & Logistics', 'Triple Dip C&CSW', 'Dbl Dip Bus & Mgt', 'Dip Eng',
                '1 Census Dip', '2+ Census Dip')

when_paid = ('at 2 weeks', '20 business days')  # Add some others later maybe. This Enum must be updated for new MOU's!

stage_enum = ('Awaiting Commencement', 'Commencement',
              'Census1', 'Census2', 'Census3', 'Census4', 'Census5', 'Census6',
              'Completion')

# These student's enrolment_status categories are under review and may change at a later date
status = ('Has Not Enrolled', 'Did Not Enrol', 'Awaiting Commencement', 'Active', 'Cancelled',
          'Not Your Student', 'No Match Found')  # These last two are for BrokerPay use only
          #  Active(Comencement) Active(Recommencement)

# enrolment_status = ('Active', 'Cancelled', 'Active Re-commenced', ...)


class MOU(db.Model):
    __tablename__ = 'mou'
    id = db.Column('mou_id', db.Integer, primary_key=True)
    title = db.Column('title', db.String(60))
    filename = db.Column('filename', db.String(40))
    effective = db.Column('effective', db.Date)
    style = db.Column('style', db.Enum(*mou_styles, name='style_enum'))
    when_paid = db.Column('when_paid', db.Enum(*when_paid, name='when_paid_enum'))
    # The "when_paid" field is for non-stage MOU's only. We are assuming that ALL staged payment are to be paid
    # as soon as practicable after the relevant stage is passed. After all, that is the whole point of this system!
    # Specifying pri & sec joins on both sides of m-to-m not necessary when backref used in Broker. SQLA fills both.
    # brokers = db.relationship('Broker', lazy='dynamic', secondary='agreed',
    #                           primaryjoin="Broker.id == agreed.c.mou_id",
    #                           secondaryjoin="MOU.id == agreed.c.mou_id"
    #                           )

    def __init__(self, name, filename, effective, style):
        self.title = name
        self.filename = filename
        self.effective = effective
        self.style = style


class PercentStage(db.Model):
    __tablename__ = 'percent_stage'
    mou_id = db.Column('mou_id', db.ForeignKey('mou.mou_id'), primary_key=True)
    delivery = db.Column('delivery', db.Enum(*delivery_enum, name='delivery_enum'), primary_key=True)
    course_type = db.Column('course_type', db.Enum(*course_types, name='course_type_enum'), primary_key=True)
    stage = db.Column('stage', db.Enum(*stage_enum, name='stage_enum'), primary_key=True)
    percent = db.Column('percent', db.Numeric)  # % of student fees due(!= received) at this stage

    def __init__(self, m, ct, s, p):
        self.mou_id = m
        self.course_type = ct
        self.stage = s
        self.percent = p


class PercentGross(db.Model):
    _tablename__ = 'percent_gross'
    mou_id = db.Column('mou_id', db.ForeignKey('mou.mou_id'),  primary_key=True)
    delivery = db.Column('delivery', db.Enum(*delivery_enum, name='delivery_enum'), primary_key=True)
    course_type = db.Column('course_type', db.Enum(*course_types, name='course_type_enum'), primary_key=True)
    stage = db.Column('stage', db.Enum(*stage_enum, name='stage_enum'), primary_key=True)
    min = db.Column('min', db.Numeric)  # These min & max are of the cost bracket, w/c determines commission
    max = db.Column('max', db.Numeric)
    percent = db.Column('percent', db.Numeric)

    def __init__(self, m, ct, s, p, bmin, bmax):
        self.mou_id = m
        self.course_type = ct
        self.stage = s
        self.min = bmin
        self.max = bmax
        self.percent = p


# At the moment it looks like the only MOU's that work by cost bracket are pct_gross and flat_fee styles,
# so simple flat fees can be dealt with in the same table by having a cost bracket like 0 .. $999999


class FlatFees(db.Model):
    __tablename__ = 'flat_fees'
    mou_id = db.Column('mou_id', db.ForeignKey('mou.mou_id'),  primary_key=True)
    delivery = db.Column('delivery', db.Enum(*delivery_enum, name='delivery_enum'), primary_key=True)
    course_type = db.Column('course_type', db.Enum(*course_types, name='course_type_enum'), primary_key=True)
    stage = db.Column('stage', db.Enum(*stage_enum, name='stage_enum'), primary_key=True)
    min = db.Column('min', db.Numeric)
    max = db.Column('max', db.Numeric)
    fee = db.Column('fee', db.Numeric)   # Hallelujah, we have a commission fee due at this stage

    def __init__(self, m, ct, s, f, bmin, bmax):
        self.mou_id = m
        self.course_type = ct
        self.stage = s
        self.min = bmin
        self.max = bmax
        self.fee = f


class User(db.Model):
    __tablename__ = 'users'  # Note that table name differs from class
    # There is already a User table in PostgreSQL that we'd clash with
    id = db.Column('user_id', db.Integer, primary_key=True)
    email = db.Column('email', db.String(40), unique=True, index=True)
    password = db.Column('password', db.String(15))
    registered_on = db.Column('registered_on', db.DateTime)
    broker_id = db.Column('broker_id', db.Integer, db.ForeignKey('broker.broker_id'))
    claims = db.relationship('Claim', lazy='dynamic')

    def __init__(self, email, password, bro):
        self.email = email
        self.password = password
        self.registered_on = datetime.utcnow()
        self.broker_id = bro

    def is_authenticated(self):
        return True  #ToDo Need some code to check if they've provided valid credentials

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return unicode(self.id)

    def __repr__(self):
        return '<User %r>' % self.email


class Claim(db.Model):
    __tablename__ = 'claim'
    id = db.Column('claim_id', db.Integer, primary_key=True)
    filename = db.Column(db.String(60))
    upload_date = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    #rcti_id = db.Column(db.Integer, db.ForeignKey('rcti.rcti_id'))
    # The above will require a rcti for every claim but it may not exist yet
    rcti = db.relationship('Rcti', uselist=False, backref='claim')
    # SA's one-to-one is implemented with a "backref" and uselist=False
    # claimed_progressions = db.relationship('Progress', lazy='dynamic', secondary='claimed',
    #                                        primaryjoin="Progress.id == claimed.c.progress_id",
    #                                        secondaryjoin="Claim.id == claimed.c.claim_id")
    claimed_list = db.relationship('Progress', secondary='claimed',
                                   backref=db.backref('claim', lazy='dynamic'),
                                   lazy='dynamic')  # Voila! A many-to-many relation in one statement.

    def __init__(self, filename, upload_date, user):
        self.filename = filename
        self.upload_date = upload_date
        self.user_id = user
        # We will populate this after parsing an uploaded .csv but before claim has been processed.
        # Claim line items must be like [Full Name, Email, Phone, Course Title, Stage Passed]
        # where Stage Passed is one of: {Enrolment, Intake, Commencement, Census1..6, Finished}


class Student(db.Model):
    __tablename__ = 'student'
    id = db.Column('student_id', db.Integer, primary_key=True)
    name = db.Column('name', db.String(40), index=True)
    email = db.Column('email', db.String(40), index=True)
    phone = db.Column('phone', db.String(25), index=True)

    def __init__(self, name, email, phone):
        self.name = name
        self.email = email
        self.phone = phone


class Taking(db.Model):
    __tablename__ = 'taking'
    id = db.Column('taking_id', db.Integer, primary_key=True)
    student_id = db.Column('student_id', db.ForeignKey('student.student_id'), primary_key=True)
    course_code = db.Column('course_code', db.ForeignKey('course.course_code'),  primary_key=True)
    contract_code = db.Column('contract_code', db.String(25), nullable=True)
    # We removed bool VFH. It's true iff there's a contract code like 'VFH00000?' on that intake
    tech1_contract = db.Column('tech1_contract', db.String(25), nullable=True)  # Used to create "Paste Special"
    # contract_code and tech1_contract should be non nullable but we'll create during parsing of a CSV and
    # then we'll have to ensure they're correctly populated later

    def __init__(self, stu, crs):
        self.student_id = stu
        self.course_code = crs
        self.contract_code = None
        self.tech1_contract = None


class Course(db.Model):
    __tablename__ = 'course'
    code = db.Column('course_code', db.String(36), primary_key=True)
    title = db.Column('title', db.String(60), nullable=False)
    # Taken from CASIS Course List? qualification_name or parent_qual... by enrolment_number

    def __init__(self, code, title):
        self.code = code
        self.title = title


class CourseTypes(db.Model):
# Split off course_types, so a course can be in more than one category
    course_code = db.Column('course_code', db.ForeignKey('course.course_code'), primary_key=True)
    mou_id = db.Column('mou_id', db.ForeignKey('mou.mou_id'), primary_key=True)
    category = db.Column('category', db.Enum(*course_types, name='course_type_enum'), nullable=False)

    def __init__(self, cc, mou, cat):
        self.course_code = cc
        self.mou_id = mou
        self.category = cat


class Location(db.Model):
    __tablename__ = 'location'
    id = db.Column('location_id', db.Integer, primary_key=True)
    tech1_code = db.Column('tech1_code', db.String(40))
    location = db.Column('location', db.String(40))

    def __init__(self, t1, loc):
        self.tech1 = t1
        self.location = loc


class CourseFees(db.Model):
    __tablename__ = 'course_fees'
    course_code = db.Column('course_code', db.ForeignKey('course.course_code'), primary_key=True)
    location_id = db.Column('location_id', db.ForeignKey('location.location_id'), primary_key=True)
    fee = db.Column('fee', db.DECIMAL)
    course = db.relationship(Course, lazy=False, primaryjoin="course.c.course_code == course_fees.c.course_code")
    location = db.relationship(Location, lazy=False, primaryjoin="location.c.location_id == course_fees.c.location_id")
    #stage = db.relationship(Stage, lazy=False, primaryjoin="stages.c.stage_id == course_fees.c.stage")

    def __init__(self, crs, loc, stage, fee):
        self.course = crs
        self.location = loc
        self.stage = stage
        self.fee = fee


# class CourseDates(db.Model):
#     __tablename__ = 'course_dates'
#     course_code = db.Column('course_code', db.ForeignKey('course.course_code'), primary_key=True)
#     stage = db.Column('stage', db.Enum(*stage_enum, name='stage_enum'), primary_key=True)
#     date = db.Column('date', db.Date)
#     # Can't use lazy='dynamic' for m-to-1, 1-to-1 or uselist=False
#     courses = db.relationship('Course', lazy='joined',
#                               primaryjoin="Course.code == course_dates.c.course_code")
#
#     def __init__(self, code, stage, date):
#         self.course_code = code
#         self.stage = stage
#         self.date = date


class Progress(db.Model):
    __tablename__ = 'progress'
    # Longer name would be "claimed_progression[student, course, stage] as we draw from uploaded claims
    id = db.Column('progress_id', db.Integer, primary_key=True)
    student_id = db.Column('student_id', db.ForeignKey('student.student_id'))
    course_code = db.Column('course_code', db.ForeignKey('course.course_code'))
    stage = db.Column('stage', db.Enum(*stage_enum, name='stage_enum'))
    delivery = db.Column('delivery', db.Enum(*delivery_enum, name='delivery_enum'), nullable=True)
    location = db.Column('location_id', db.ForeignKey('location.location_id'))
    claims = db.relationship('Claim', lazy='dynamic', secondary='claimed',
                             primaryjoin="Progress.id == claimed.c.progress_id",
                             secondaryjoin="Claim.id == claimed.c.claim_id")

    def __init__(self, stu, crs, stage):
        self.student_id = stu
        self.course_code = crs
        self.stage = stage
        self.delivery = None  # This may be popl8d l8r in match() when known


class Claimed(db.Model):
    __tablename__ = 'claimed'
    claim_id = db.Column('claim_id', db.ForeignKey('claim.claim_id'), primary_key=True)
    #student_id = db.Column('student_id', db.Integer, db.ForeignKey('student.student_id'), primary_key=True)
    #course_code = db.Column('course_code', db.ForeignKey('course.course_code'), primary_key=True)
    #stage = db.Column('stage', db.Enum(*stage_enum), primary_key=True)
    progress_id = db.Column('progress_id', db.ForeignKey('progress.progress_id'), primary_key=True)
    # I am objectifying progressions so I think this is OK, hopefully SA will go along with it.
    status = db.Column('status', db.Enum(*status, name='status_enum'), nullable=True)  # Updated later in match()
    payable = db.Column('payable', db.Boolean, nullable=True)  # Derived value - from claimed, payable & rcti tables
    census_date = db.Column('census_date', db.Date, nullable=True)  # Next census - calc l8r in match() with CASIS data

    def __init__(self, claim, pro):
        self.claim_id = claim
        self.progress_id = pro
        self.status = None
        self.payable = False
        self.census_date = None


class Payable(db.Model):
    __tablename__ = 'payable'
    #student_id = db.Column('student_id', db.ForeignKey('student.student_id'), primary_key=True)
    #course_code = db.Column('course_code', db.ForeignKey('course.course_code'), primary_key=True)
    #stage = db.Column('stage', db.Enum(*stage_enum, name='stage_enum'), primary_key=True)
    progress_id = db.Column('progress_id', db.Integer, db.ForeignKey('progress.progress_id'), primary_key=True)
    rcti_id = db.Column('rcti_id', db.Integer, db.ForeignKey('rcti.rcti_id'))
    # progressions = db.relationship('Progress', lazy='joined',
    #                                primaryjoin="progress.c.id == payable.c.progress_id")

    def __init__(self, pro, rcti):
        self.progress_id = pro
        self.rcti_id = rcti


class Rcti(db.Model):
    __tablename__ = 'rcti'  # Recipient Created Tax Invoice (as in recipient of the service, that's us)
    id = db.Column('rcti_id', db.Integer, primary_key=True)
    claim_id = db.Column('claim_id', db.Integer, db.ForeignKey('claim.claim_id'))
    amount = db.Column('amount', db.DECIMAL, nullable=True)  # Update later after payable progressions linked
    po_num = db.Column('po_num', db.String(15), nullable=True)  # Purchase Order may be created later
    processed = db.Column('processed', db.DateTime, nullable=True)  # Processing in Tech1 occurs later
    # PO num is reqd on Rcti before payment can be made from TechOne.

    def __init__(self, claim):
        self.claim_id = claim
        # self.amount = amount
        # self.po_num = po_num
        # self.processed = processed    # On entry of po_num, processed = datetime.utcnow()

'''
class RateHistory(db.Model):
    __tablename__ = 'rate_history'
    mou_id = db.Column('mou_id', db.Integer, db.ForeignKey('mou.mou_id'), primary_key=True)
    date_from = db.Column('date_from', db.Date, primary_key=True)
    delta_rate = db.Column('delta_rate', db.Float)  #  best practice for keeping history

    def __init__(self, mou_id, date_from, delta_rate):
        self.mou_id = mou_id
        self.date_from = date_from
        self.delta_rate = delta_rate
'''


# ####################################################################################
#   Cue the CASIS enrolment table (and other assorted data from CASIS)       #########
# ####################################################################################
# class Intake(db.Model):
#     __tablename_ = 'intake'
#     id = db.Column('intake_id', db.Integer, primary_key=True)
#     intake_name = db.Column('intake_name', db.String(50), primary_key=True)
#     enrol_num = db.Column('enr_num', db.ForeignKey('enrolment.enrolment_number'))
#     census_date = db.Column('census_date', db.DateTime)
#
#     def __init__(self, intake, enrol, census, contract):
#         self.intake_name = intake
#         self.enrol_num = enrol
#         self.census_date = census


# class Contract(db.Model):
#     __tablename__ = 'contract'
#     student = db.Column('student_id', db.ForeignKey('student.student_id'), primary_key=True)
#     course = db.Column('course_code', db.ForeignKey('course.course_code'), primary_key=True)
#     code = db.Column('contract_code', db.String(40), primary_key=True)
#     tech1 = db.Column('tech1_code', db.String(40))
#
#     def __init__(self, student, course, code, tech1):
#         self.student = student
#         self.course = course
#         self.code = code
#         self.tech1 = tech1


class Enrolment(db.Model):
    __tablename__ = 'enrolment'
    id = db.Column('enrolment_id', db.Integer, primary_key=True)
    enrolment_number = db.Column('enrolment_number', db.String(15), nullable=False, index=True)
    student_account_name = db.Column('student_account_name', db.String(40), index=True)
    student_person_account_mobile = db.Column('student_person_account_mobile', db.String(15), index=True)
    student_person_account_email = db.Column('student_person_account_email', db.String(40), index=True)
    referral_source = db.Column('referral_source', db.String(60), index=True)
    form_number = db.Column('form_number', db.String(15))
    enrolment_status = db.Column('enrolment_status', db.String(25))
    enrolment_start_date = db.Column('enrolment_start_date', db.Date)
    cancellation_date = db.Column('cancellation_date', db.Date, index=True)
    cancellation_reason = db.Column('cancellation_reason', db.String(100))
    contract_code = db.Column('contract_code', db.String(20))
    campus_name = db.Column('campus_name', db.String(40))
    qualification_name = db.Column('qualification_name', db.String(60))
    delivery_mode = db.Column('delivery_mode', db.String(40))  # {'Classroom Based', 'Electronic Based'}
    census_date = db.Column('census_date', db.Date, nullable=True, index=True)
    qualification_course_id = db.Column('qualification_course_id', db.String(80), index=True)

    def __init__(self, enrolment_number, student_account_name, student_person_account_mobile, student_person_account_email,
                 referral_source, form_number, enrolment_status, enrolment_start_date, cancellation_date,
                 cancellation_reason, contract_code, campus_name, qualification_name, delivery_mode, census_date,
                 qualification_course_id):
        self.enrolment_number = enrolment_number
        self.student_account_name = student_account_name
        self.student_person_account_mobile = student_person_account_mobile
        self.student_person_account_email = student_person_account_email
        self.referral_source = referral_source
        self.form_number = form_number
        self.enrolment_status = enrolment_status
        self.enrolment_start_date = enrolment_start_date
        self.cancellation_date = cancellation_date
        self.cancellation_reason = cancellation_reason
        self.contract_code = contract_code
        self.campus_name = campus_name  # == delivery_location? If = 'Online' ==> 'Electronic Based'?
        self.qualification_name = qualification_name
        self.delivery_mode = delivery_mode
        self.census_date = census_date
        self.qualification_course_id = qualification_course_id


class Form(db.Model):
    __tablename__ = 'form'
    id = db.Column('form_id', db.Integer, primary_key=True)
    form_name = db.Column('form_name', db.String(10), primary_key=True)
    student_name = db.Column('student_name', db.String(40), index=True)
    student_mobile_number = db.Column('student_mobile_number', db.String(15), index=True)
    student_email = db.Column('student_email', db.String(40), index=True)
    delivery_mode = db.Column('delivery_mode', db.String(20))  # {'Class Room', 'Online'}
    delivery_location = db.Column('delivery_location', db.String(40))
    form_status = db.Column('form_status', db.String(15), index=True)
    parent_qualification = db.Column('parent_qualification', db.String(80))
    referral_source = db.Column('referral_source', db.String(40))
    form_submitted_date = db.Column('form_submitted_date', db.DateTime)

    def __init__(self, form_name, student_name, student_mobile_number, student_email, delivery_mode,
                 delivery_location, form_status, parent_qualification, referral_source, form_submitted_date):
        self.form_name = form_name
        self.student_name = student_name
        self.student_mobile_number = student_mobile_number
        self.student_email = student_email
        self.delivery_mode = delivery_mode
        self.delivery_location = delivery_location
        self.form_status = form_status
        self.parent_qualification = parent_qualification
        self.referral_source = referral_source
        self.form_submitted_date = form_submitted_date


class Opportunity(db.Model):
    __tablename__ = 'opportunity'
    id = db.Column('opportunity_id', db.Integer, primary_key=True)
    opportunity_name = db.Column('opportunity_name', db.String(30), index=True)
    account_name = db.Column('account_name', db.String(30), index=True)
    phone = db.Column('phone', db.String(15))
    contact_email = db.Column('contact_email', db.String(40), index=True)
    primary_campaign_source = db.Column('primary_campaign_source', db.String(40), index=True)
    stage = db.Column('stage', db.String(20), index=True)
    course_name = db.Column('course_name', db.String(60), index=True)
    enrolment_stage = db.Column('enrolment_stage', db.String(50))
    delivery_type = db.Column('delivery_type', db.String(50))  # {'Class Room', 'Online'}
    created_date = db.Column('created_date', db.Date)

    def __init__(self, opportunity_name, account_name, phone, contact_email, primary_campaign_source,
                 stage, course_name, enrolment_stage, delivery_type, created_date):
        self.opportunity_name = opportunity_name
        self.account_name = account_name
        self.phone = phone
        self.contact_email = contact_email
        self.primary_campaign_source = primary_campaign_source
        self.stage = stage
        self.course_name = course_name
        self.enrolment_stage = enrolment_stage
        self.delivery_type = delivery_type
        self.created_date = created_date


# ####################################################
# End of data model with SQL Alchemy defined classes
# ###################################################

class Possibles3(db.Model):  # Temp table repln of Opportunity for match()
    __tablename__ = 'possibles3'
    id = db.Column('possibles3_id', db.Integer, primary_key=True)
    opportunity_name = db.Column('opportunity_name', db.String(30), index=True)
    account_name = db.Column('account_name', db.String(30), index=True)
    phone = db.Column('phone', db.String(15))
    contact_email = db.Column('contact_email', db.String(40), index=True)
    primary_campaign_source = db.Column('primary_campaign_source', db.String(40), index=True)
    stage = db.Column('stage', db.String(20), index=True)
    course_name = db.Column('course_name', db.String(60), index=True)
    enrolment_stage = db.Column('enrolment_stage', db.String(50))
    delivery_type = db.Column('delivery_type', db.String(50))  # {'Class Room', 'Online'}
    created_date = db.Column('created_date', db.Date)

    def __init__(self, opportunity_name, account_name, phone, contact_email, primary_campaign_source,
                 stage, course_name, enrolment_stage, delivery_type, created_date):
        self.opportunity_name = opportunity_name
        self.account_name = account_name
        self.phone = phone
        self.contact_email = contact_email
        self.primary_campaign_source = primary_campaign_source
        self.stage = stage
        self.course_name = course_name
        self.enrolment_stage = enrolment_stage
        self.delivery_type = delivery_type
        self.created_date = created_date


class Possibles1(db.Model):   # ToDo: Remove the need for these duplicate tables for holding temp results in match()
    __tablename__ = 'possibles1'
    id = db.Column('possibles1_id', db.Integer, primary_key=True)
    enrolment_number = db.Column('enrolment_number', db.String(15), nullable=False, index=True)
    student_account_name = db.Column('student_account_name', db.String(40), index=True)
    student_person_account_mobile = db.Column('student_person_account_mobile', db.String(15), index=True)
    student_person_account_email = db.Column('student_person_account_email', db.String(40), index=True)
    referral_source = db.Column('referral_source', db.String(60), index=True)
    form_number = db.Column('form_number', db.String(15))
    enrolment_status = db.Column('enrolment_status', db.String(25))
    enrolment_start_date = db.Column('enrolment_start_date', db.Date)
    cancellation_date = db.Column('cancellation_date', db.Date, index=True)
    cancellation_reason = db.Column('cancellation_reason', db.String(100))
    contract_code = db.Column('contract_code', db.String(20))
    campus_name = db.Column('campus_name', db.String(40))
    qualification_name = db.Column('qualification_name', db.String(60))
    delivery_mode = db.Column('delivery_mode', db.String(40))  # {'Classroom Based', 'Electronic Based'}
    census_date = db.Column('census_date', db.Date, nullable=True, index=True)
    qualification_course_id = db.Column('qualification_course_id', db.String(80), index=True)

    def __init__(self, enrolment_number, student_account_name, student_person_account_mobile, student_person_account_email,
                 referral_source, form_number, enrolment_status, enrolment_start_date, cancellation_date,
                 cancellation_reason, contract_code, campus_name, qualification_name, delivery_mode, census_date,
                 qualification_course_id):
        self.enrolment_number = enrolment_number
        self.student_account_name = student_account_name
        self.student_person_account_mobile = student_person_account_mobile
        self.student_person_account_email = student_person_account_email
        self.referral_source = referral_source
        self.form_number = form_number
        self.enrolment_status = enrolment_status
        self.enrolment_start_date = enrolment_start_date
        self.cancellation_date = cancellation_date
        self.cancellation_reason = cancellation_reason
        self.contract_code = contract_code
        self.campus_name = campus_name  # == delivery_location? If = 'Online' ==> 'Electronic Based'?
        self.qualification_name = qualification_name
        self.delivery_mode = delivery_mode
        self.census_date = census_date
        self.qualification_course_id = qualification_course_id

# ###########
@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    get_flashed_messages()  # provides feedback and debugging msgs
    #dbg return redirect(url_for('claims'))
    return redirect(url_for('login'))  # Might later have separate index and login pages.


@app.route('/login', methods=['GET', 'POST'])
# Are you The Gatekeeper?
def login():
    #Doesn't seem to make any diff  # get_flashed_messages()
    if request.method == 'GET':
        return render_template('index.html')
        #return redirect(url_for('claims'))  # dbg
    #if request.method == 'POST':
    email = request.form['email']
    password = request.form['password']
    # remember_me = False
    # if 'remember_me' in request.form:
    #     remember_me = True

    registered_user = User.query.filter(User.email == email).scalar()  # Unique index on this col.
    #flash(u'usr: ' + User.email + u'  ' + u'reg. on: ' + (User.registered_on))  #Causing "not JSON serializable" err?
    if registered_user:
        if registered_user.password == password:
            login_user(registered_user)  # , remember=remember_me)
            flash(u'User logged in: ' + registered_user.email)
            return redirect(url_for('claims'))  # (request.args.get('next') or url_for(
    else:
        flash(u'That username/password combination is unknown.')  # , 'error')
        return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    # else POST, let's do this
    broker = Broker.query.filter_by(orgname=request.form['broker'])
    broker_id = broker.id
    if broker_id:  # ie. not None
        user = User(request.form['email'], request.form['password'], broker_id)
    else:
        flash("Sorry, we don't know that broker(yet.) Please try again.")
        broker = Broker(request.form['broker'], request.form['abn'])
        db.session.add(broker)
        db.sesion.commit()
        return redirect(url_for('register'))
    db.session.add(user)
    db.session.commit()
    flash('New user registered')
    return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    logout_user()  # from Flask-Login extension
    return redirect(url_for('index'))


@app.before_request
def before_request():
    g.user = current_user


@app.route('/downloads/<path:filename>')  # ToDo:  sort this out up or down!
def uploaded_file(filename):
    uploads_path = app.config['UPLOAD_FOLDER']  # + '/' + g.user.user_id
    return send_from_directory(uploads_path, filename)


@app.route('/claims', methods=['GET', 'POST'])
def claims():
    # Send to claims page a select result where each line is a claim by SA's current_user
    # lines ~ [id, filename, upload_date, count, referrals, rcti_num, po_num, processed, amount]
    # This is a LEFT OUTER JOIN -- nulls for rows in CLAIMED where there's no entry in PAYABLE
    sql_str = text("select cl.claim_id, filename, upload_date, "
                   + "  (select count(*) from claimed "
                   + "   where claimed.claim_id = cl.claim_id) as count, "
                   + "  (select count(*) from payable, claimed, rcti "
                   + "   where payable.progress_id = claimed.progress_id "
                   + "   and claimed.claim_id = cl.claim_id "
                   + "   and rcti.rcti_id = payable.rcti_id "
                   + "   and rcti.claim_id = cl.claim_id "
                   + "   and cl.user_id = :user) as referrals, "
                   + "rcti_id, processed, amount "
                   + "from claim cl left join rcti "
                   + "on rcti.claim_id = cl.claim_id "
                   + "where cl.user_id = :user "
                   )
    ## Now, how to do the above in the glorious SQL Alchemy syntax
    # claims_sel = select([Claim.id
    #              + "," + Claim.filename
    #              + "," + Claim.upload_date
    #              + "," + Claimed.query.filter(Claimed.claim_id == Claim.id).count()
    #              + "," + Payable.query.join(Claimed, Payable.progress_id == Claimed.progress_id)
    #                             .filter(Claimed.claim_id == Claim.id)
    #                             .count()
    #              + "," + Rcti.id
    #              + "," + Rcti.po_num
    #              + "," + Rcti.processed
    #              + "," + Rcti.amount
    #                      ]).correlate(None) \
    #     .select_from(Claimed.query
    #     .outerjoin(Payable, Claimed.progress_id == Payable.progress_id)
    #     .join(Claim, Claim.id == Claimed.claim_id)
    #     .join(Rcti, Rcti.id == Claim.rcti)
    #     .filter(Rcti.claim_id == Claim.id)
    #     .order_by(Claim.upload_date.desc())
    #     )
    # claims_recs = Claimed.query\
    #     .filter(claims_sel) \
    #     .filter(Claim.user_id == current_user) \
    #     .all()
    ##Err: "Can't adapt type 'LocalProxy'
    # At this point Michael Bayer, I can't be bothered anymore
    # So, raw SQL, here we go now.
    conn = db.engine.connect()
    the_current_user = g.user  # = current_user  # Flask login var
    # ToDo -- IMPORTANT REQUIREMENT: Keep different user's claims separate so they can't see others' claims.
    claims_recs = conn.execute(sql_str, user=the_current_user.id).fetchall()
    return render_template('claims.html', lines=claims_recs)


@app.route('/claims/<int:claim_id>', methods=['GET'])
#dbg @login_required
def claim_details(claim_id):
    cl = Claim.query.get_or_404(claim_id)  # .scalar()? .first()? There can be only one!
    # Flask provides get_or_404() and first_or_404() in case get returns None
    if cl is None:
        return redirect(url_for('claims'))
    # <th> Name  E-mail  Phone  Course  Stage  Payable  Status  PO#  $
    # $ = Sum(claimed items deemed payable)    # ToDo  where claim_id = :claim

    sql_str = text("  select student.student_id as stu_id, student.name, student.email, student.phone, "
                   + "       course.title, progress.stage, "
                   + "       claimed.payable as payable, "
                   + "       claimed.census_date as next_census, "
                   + "       claimed.status as status, "
                   + "       payable.rcti_id as rcti "
                   + "from claimed left outer join payable on payable.progress_id = claimed.progress_id "
                   + "join claim on claim.claim_id = claimed.claim_id "
                   + "join progress on progress.progress_id = claimed.progress_id "
                   + "join student on student.student_id = progress.student_id "
                   + "join course on course.course_code = progress.course_code "
                   + "left outer join rcti on rcti.rcti_id = payable.rcti_id "
                   + "where claim.claim_id = :clm "
                   )  # or maybe not left outer join rcti, just use join payable on progress_id
                   #  + "join enrolment on enrolment.student_account_name = student.name "
                   # joining on enrolment stuffs things up because it produces duplicates
                   # + "       enrolment.enrolment_status as status, "
    # Assume: Enrolment.name has been updated(for the mo, in our local copy only) to the correct name
    # based on a positive match on phone and/or email address if there was no initial match on name.
    #ToDo: The spelling of the name may be wrong on the broker's claim or in CASIS. How to decide??
    # sub_qry = Student.query.join("claimed", "course", "course_dates") \
    #                  .filter(claimed.claim_id == claim.id).subquery()
    # An SA subquery returns a "selectable" which is as for select()
    #claim_data = Claimed.query.filter(sql_str).filter(claim_id == clmid).all()

    conn = db.engine.connect()  # Raw SQL, here we go now.
    claim_data = conn.execute(sql_str, clm=claim_id).fetchall()

    if True:  # dbg this g.user stuff: claim_rec.user_id == g.users.user_id:
        return render_template('claim_detail.html', claim_items=claim_data)
    else:
        flash('You are not authorized to view/edit this item', 'error')
        return redirect(url_for('claims'))


@app.route('/download_template')
def download_template():
    return redirect(url_for('/download/claim_template.csv'))


@app.route('/new_mou', methods=['GET', 'POST'])
# gav Anon mixin no attr user_id caused by #@login_required
# ToDo Need to verify current user is admin before accessing this page
def new_mou():
    if request.method == 'GET':
        return render_template('new_mou.html')
    else:  # So method = 'POST', data is being submitted
        if not request.form['filename']:
            flash('A file name is required', 'error')
        elif not request.form['effective']:
            flash('An effective date is required', 'error')
        else:
            mou = MOU(request.form['title'], request.form['filename'], request.form['effective'])
            db.session.add(mou)
            db.session.commit()
            flash(u'Claim line entry was successful.')
            return redirect(url_for('pain_point'))  # ToDo form for entry of pay points by stage


'''
@app.route('/admin/<int:mou_id>', methods=['GET', 'POST'])
@login_required
def show_or_update(mou_id):
    # the rest is based on claim, refactor claim -> mou
    claim_rec = Claim.query.get(claim_id)
    if claim_rec.users.user_id == g.users.user_id:
        if request.method == 'GET':
            return render_template('claim_detail.html', claim=claim_rec)
        claim_rec.filename = request.form['title']
        claim_rec.upload_date = request.form['upload_date']
        claim_rec.referrals = 0  # compute this by parsing .csv file!
        claim_rec.done = ('done.%d' % claim_id) in request.form
        db.session.commit()
        return redirect(url_for('claims'))
    else:
        flash('You are not authorized to view/edit this item', 'error')
 '''


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ['csv', 'CSV', 'sql', 'txt', 'pdf', 'PDF', 'xlsx']
           # ToDo Remove options for .sql et. al.


@app.route('/upload_instrns', methods=['GET'])
def upload_instrns():
    return render_template('upload_help.html')


@app.route('/upload_claim', methods=['GET', 'POST'])
def upload_claim():
    # file comes from the files dictionary on the request
    if request.method == 'POST':
        csv_file = request.files['csv_file']  # form dict
        if csv_file and allowed_file(csv_file.filename):  # ie. a .csv file
            filename = secure_filename(csv_file.filename)
            csv_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            # ToDo Save files to $UPLOAD_FOLDER/g.user.user_id for data security?
            # New file saved in DATA_DIR
            claim = Claim(filename, datetime.utcnow(), current_user.id)
            # final 'done' field init to False as hasn't been validated
            db.session.add(claim)
            db.session.commit()
            parse_csv(filename, claim)  # read the data in to claimed progressions table
        return redirect(url_for('claims'))
    else:  # method='GET' ie. not submitting form
        return render_template('upload_claim.html')


@app.route('/rcti/<int:rcti_id>', methods=['GET'])
def rcti(rcti_id):
    # Display an HTML Recipient Created Tax Invoice for a given rcti_id
    inv_num = 'Rcti-00' + str(rcti_id)
    the_claim = (Rcti.query.filter(Rcti.id == rcti_id).scalar()).claim_id  # .scalar? There can be only one!
    the_user = (Claim.query.filter(Claim.id == the_claim).scalar()).user_id
    the_broker = (User.query.filter(User.id == the_user).scalar()).broker_id
    broker = Broker.query.filter(Broker.id == the_broker).scalar()
    # I might need various objects:
    # [broker.orgname, broker.address, broker.suburb, broker.state, broker.postcode, broker.abn]
    date = (Rcti.query.filter(Rcti.id == rcti_id).scalar()).processed
    day = date.day
    month = date.month
    year = date.year
    broker_data = {'day': day, 'month': month, 'year': year, 'inv_num': inv_num,
                   'supplier': broker.orgname,
                   'address': broker.address,
                   'suburb': broker.suburb,
                   'state': broker.state,
                   'postcode': broker.postcode,
                   'abn': broker.abn
                   }
    # MOU tables should be refactored to include style in the key.
    # Now choose MOU with the most recent effective date (assuming no one puts in future dated MOU's!
    the_mou = MOU.query.join(agreed, MOU.id == agreed.c.mou_id)\
        .join(Broker, Broker.id == agreed.c.broker_id)\
        .filter(Broker.id == the_broker)\
        .order_by(desc(MOU.effective)).first().id  # Assuming chronological order, last is most recent.

    contract_style = MOU.query.filter(MOU.id == the_mou).scalar().style
    flash(u'The relevant MOU is: ' + str(the_mou))
    if contract_style == 'flat_fee':   # .get(Student.name, Course.title, Progress.stage)
        # current_progs = Progress.query.join(Student, Student.id == Progress.student_id)\
        #     .join(Course, Course.code == Progress.course_code)\
        #     .join(Payable, Payable.progress_id == Progress.id)\
        #     .filter(Payable.rcti_id == rcti_id)\
        #     .join(select([Student.name, Course.title, Progress.stage])
        #           .where(Student.id == Progress.student_id), Progress.id)\
        #     .all()
        # flash(u'The payable progressions are: ' + str(current_progs))
        #     .join(CourseFees, CourseFees.course_code == Progress.course_code)\
        #     .filter(CourseFees.stage == Progress.stage)\
        items_sql = text("select student.name, course.title, progress.stage, "
                         + "       flat_fees.fee as comm, "
                         + "       flat_fees.fee * 0.10 as gst, "
                         + "       flat_fees.fee * 1.10 as price "
                         + "  from student, course, course_types, progress, claimed, payable, rcti, mou, flat_fees "
                         + " where student.student_id = progress.student_id "
                         + "   and course.course_code = progress.course_code "
                         + "   and progress.progress_id = payable.progress_id "
                         + "   and claimed.progress_id = progress.progress_id "
                         + "   and claimed.census_date < now()::date "
                         + "   and payable.progress_id = progress.progress_id "
                         + "   and payable.rcti_id = rcti.rcti_id "
                         + "   and payable.rcti_id =  :rcti "
                         + "   and mou.mou_id = :mou "
                         + "   and course_types.mou_id = mou.mou_id "
                         + "   and course_types.course_code = course.course_code "
                         + "   and flat_fees.course_type = course_types.category "
                         + "   and flat_fees.mou_id = mou.mou_id "
                         + "   and flat_fees.delivery = progress.delivery "
                         + "   and flat_fees.stage = progress.stage "
                         + "   and flat_fees.max = 999999 "
                         + "   and flat_fees.min = 0 "
                         )   # + "join enrolment on enrolment.student_account_name = student.name "
                             # joining on enrolment stuffs things up because it's de-normalised and has duplicates
    elif contract_style == 'pct_gross':
        current_progs = Progress.query\
            .join(Student, Student.id == Progress.student_id)\
            .join(Course, Course.code == Progress.course_code)\
            .join(Payable, Payable.progress_id == Progress.id)\
            .filter(Payable.rcti_id == rcti_id)\
            .all()
            # .join(CourseDates, CourseDates.course_code == Course.code)\
            # .filter(CourseDates.stage == Progress.stage)\
            # .filter(CourseDates.date <= datetime.utcnow().date())\
            # .all()
        #dbg flash(u'The payable progressions are: ' + str(current_progs))

        items_sql = text("select student.name, course.title, progress.stage, "
                         + "     percent_gross.percent * course_fees.fee as comm, "
                         + "     percent_gross.percent * course_fees.fee * 0.10 as gst, "
                         + "     percent_gross.percent * course_fees.fee * 1.10 as price "
                         + "from student, course, progress, payable, mou, rcti, "
                         + "     course_fees, course_types, claimed, location, percent_gross "
                         + "where student.student_id = progress.student_id "
                         + "   and course.course_code = progress.course_code "
                         + "   and payable.progress_id = progress.progress_id "
                         + "   and claimed.progress_id = progress.progress_id "
                         + "   and claimed.census_date < now()::date "
                         + "   and payable.rcti_id = rcti.rcti_id "
                         + "   and payable.rcti_id =  :rcti "
                         + "   and mou.mou_id = :mou "
                         + "   and course_fees.course_code = course.course_code "
                         + "   and course_fees.location_id = location.location_id "
                         + "   and course_types.course_code = course.course_code "
                         + "   and course_types.mou_id = mou.mou_id "
                         + "   and percent_gross.course_type = course_types.category "
                         + "   and percent_gross.delivery = progress.delivery "
                         + "   and percent_gross.stage = progress.stage "
                         + "   and percent_gross.min < course_fees.fee "
                         + "   and course_fees.fee < percent_gross.max "
                         )   # + "join enrolment on enrolment.student_account_name = student.name "
                             # joining on enrolment stuffs things up because it's de-normalised and has duplicates
    elif contract_style == 'pct_stage':
        items_sql = text("select student.name, course.title, progress.stage, "
                         + "       percent_stage.percent * course_fees.fee * as comm, "
                         + "       percent_stage.percent * course_fees.fee * 0.10 as gst, "
                         + "       percent_stage.percent * course_fees.fee * 1.10 as price "
                         + "from student, course, progress, payable, mou, rcti, "
                         + "     course_fees, course_types, claimed, location, percent_stage "
                         + "   and course.course_code = progress.course_code "
                         + "   and payable.progress_id = progress.progress_id "
                         + "   and payable.rcti_id =  :rcti "
                         + "   and mou.mou_id = :mou "
                         + "   and course_fees.course_code = course.course_code "
                         + "   and course_fees.location_id = location.location_id "
                         + "   and course_types.course_code = course.course_code "
                         + "   and course_types.mou_id = mou.mou_id "
                         + "   and percent_stage.course_type = course_types.category "
                         + "   and percent_stage.delivery = progress.delivery "
                         + "   and percent_stage.stage = progress.stage "
                         + "   and percent_stage.min < course_fees.fee "
                         + "   and course_fees.fee < percent_stage.max "
                         )   # + "join enrolment on enrolment.student_account_name = student.name "
                             # joining on enrolment stuffs things up because it's de-normalised and has duplicates
    else:  # Something's gone wrong.
        # Add some error trapping here. Redirect to generic error page?
        flash(u'Something has gone wrong! This Rcti seems to have no MOU associated with it.')
        pass

    # Now execute whichever query we chose, to get the line items for the Rcti and calc totals
    # Raw SQL, here we go now.
    conn = db.engine.connect()
    line_items = conn.execute(items_sql, rcti=rcti_id, mou=the_mou).fetchall()
    # flash(u'The current line items are: ' + str(line_items))
    # line_items is a list of tuples, access y [0..5]?
    totals = {'value_total': sum(tup[3] for tup in line_items),
              'gst_total': sum(tup[4] for tup in line_items),
              'price_total': sum(tup[5] for tup in line_items)}
    return render_template('rcti.html', broker_data=broker_data, line_items=line_items, totals_data=totals)


def validated(row):
    # This row should pass basic type checks.
    name = row["Name"]
    email = row["Email"]
    phone = row["Phone"]
    course = row["Course"]
    stage = row["Stage"]
    #dbg flash(str(name) +' | '+ str(email) +' | '+ str(phone) +' | '+ str(course) +' | '+ str(stage))
    if stage.capitalize() not in \
            ['Awaiting Commencement', 'Commencement', 'Completion',
             'Census1', 'Census2', 'Census3', 'Census4', 'Census5', 'Census6',
             'Census 1', 'Census 2', 'Census 3', 'Census 4', 'Census 5', 'Census 6']:
        return False
    if name == "":
        return False
    #if not phone_format(phone):
    #    return False
    if course == "":
        return False
    return True


def parse_csv(filename, claim):
    # Ultimately want to check data against Salesforce!
    tax_inv = Rcti(claim.id)  # This has no data in it yet. Delete it if it ends up empty
    db.session.add(tax_inv)
    db.session.commit()
    flash(u'Rcti#: ' + str(tax_inv.id) + '    claim#: ' + str(tax_inv.claim_id)) #dbg
    csv_path = app.config['UPLOAD_FOLDER'] + filename
    with open(csv_path, "rb") as file_obj:
        reader = csv.DictReader(file_obj, delimiter=",", quotechar="'")  # ToDo I think double quote is std for Excel
        for row in reader:
            # data row template
            # ["Name", "Email", "Phone", "Course", "Stage"]
            if False:  # not validated(row):  # Do some basic checks re alpha, numeric etc.
                flash(u'Your uploaded data does not appear to be in the correct format')
                return  # ie. to redirect(url_for('claims')) in /upload_claim
            else:
                name = row["Name"]
                email = row["Email"]
                phone = row["Phone"]

                student = Student(name, email, phone)
                db.session.add(student)
                db.session.commit()  # Note student table is short for "claimed_student" as we take any input

                course_claimed = (row["Course"])  # In order to use this we'd need to ensure all
                # course titles are capitalized on all letters incl 'of', 'in' etc.
                all_caps_title = course_claimed.upper()  # Convert input to ALL UPPER CASE
                course = Course.query.filter(Course.title == all_caps_title).scalar()
                if course is None:
                    course_code = 'Test0'  # Could make this a special course_code for  "COURSE TITLE NOT FOUND"
                else:
                    course_code = course.code
                stage = (row["Stage"]).capitalize()  # We'll accept all caps or all lower CENSUS 1 -> Census 1
                bro_id = User.query.join(Claim, User.id == Claim.user_id)\
                                   .filter(Claim.id == claim.id)\
                                   .scalar().broker_id  # There should be exactly one broker associated.
                # sql = text("select broker_id from users, claim "
                #            "where users.user_id = claim.user_id "
                #            "and claim.claim_id = :clm_id")
                # This should give me a unique broker id.
                broker = Broker.query.get(bro_id)
                #flash(u'Before match(), we have: ' + str(student.name) + ' | ' + course_code + ' | ' + stage)  #dbg
                # This is where the matching gets called.
                # Returns { 'status':  , 'payable':  , 'census_date':  , 'delivery':  , 'location':  }

                # ***************************************************************************************************
                match_results = match(name, email, phone, broker.orgname, all_caps_title, stage)  # *****************
                # ***************************************************************************************************

                progress = Progress(student.id, course_code, stage)
                progress.delivery = match_results["delivery"]
                loc_name = match_results["location"]
                if loc_name:
                    loc_id = Location.query.filter(Location.location == loc_name).first().id  #ToDo Cope with non-unique?
                else:
                    loc_id = None
                progress.location = loc_id
                db.session.add(progress)
                db.session.commit()  # Have to commit after each object created or it's not in the DB

                if match_results["status"] not in ['Has Not Enrolled', 'Did Not Enrol', 'No Match Found']:
                    taking = Taking(student.id, course_code)
                    db.session.add(taking)
                    db.session.commit()

                claimed = Claimed(claim.id, progress.id)  # Following 3 fields are not needed by __init__
                claimed.status = match_results['status']
                claimed.payable = match_results['payable']
                claimed.census_date = match_results['census_date']
                db.session.add(claimed)
                db.session.commit()

                # Pay up if status not in ['Awaiting Commencement', 'Has Not Enrolled', 'Did Not Enrol',
                #                          'Not Your Student', 'No Match Found']  ie. either 'Active' or 'Cancelled'
                # ***********************  This is where the payment workflow is initiated  ***********************
                if match_results['payable']:
                    payable = Payable(progress.id, tax_inv.id)  # We need to link this "progression" to the Rcti
                    db.session.add(payable)
                    db.session.commit()
                if match_results['status']:
                    flash(' | ' + u'status: ' + match_results["status"])
                else:
                    flash(' | ' + u'status: None!!!!')
                # flash(u'The current progression is: ' + str(progress.student_id) + ' | ' + progress.course_code
                #       + ' | ' + progress.stage + u' payable: ' + str(match_results["payable"]))  # dbg

        # The extra data for an Rcti(po_num and date_processed) will be updated later by Accounts Payable.
        # We should only add and commit the Rcti if there are some payable progressions against it
        progs = Payable.query.filter(Payable.rcti_id == tax_inv.id).all()
        if not progs:  # ie. Rcti has no rows empty
            db.session.delete(tax_inv)
            db.session.commit()
        else:
            calc_amt_rcti(tax_inv.id)  # This fn will use the data entered in the DB to calculate the total amount.
        # The file gets auto closed by the with stmt.
        # It should all be in the DB now so... we should be ok to DELETE the file immediately!
        if os.path.isfile(csv_path):
            os.remove(csv_path)


def match(stu, eml, pho, broker, title_all_upper, stage):
    # This function is a "priority matching algorithm" designed by Samuel Bunting in Excel. It takes data
    # from tables Enrolment, Form and Opportunity in CASIS and returns a dict of data to be used to update
    # the BrokerPay tables CLAIMED, PROGRESS and TAKING with the results dict.
    results = {'status': None,  'payable': False,  'census_date': None,  'delivery': None,  'location': None}
    # claimed student status = {enrolment_status} U {'Not Your Student', 'No Match Found', 'Did Not Enrol'}

    # Would it might be easier for people to understand SQL rather than itertools? Is itertools maybe faster?
    # poss1_cols = ('possibles1_id', 'enrolment_number', 'student_account_name', 'student_person_account_mobile',
    #               'student_person_account_email', 'referral_source', 'form_number', 'enrolment_status',
    #               'enrolment_start_date', 'cancellation_date', 'cancellation_date', 'cancellation_reason',
    #               'contract_code', 'campus_name', 'qualification_name', 'delivery_mode', 'census_date',
    #               'qualification_course_id')
    # #dict(zip(((c.key for c in table.c), row))  # Create a dictionary to use for insert into Possibles1
    # ((c.key for c in poss1.c), tuple)
    # for tup in poss1:
    #     Possibles1.__table__     # .insert(dict(zip(poss1_cols, tup)))  # This insert fails for some reason

    poss_enrs = casis_get('Enrolment', 'student_account_name', "'"+stu+"'")
    flash(u'Claimed student: ' + str(stu))  # dbg
    # poss_enrs = Enrolment.query.filter(Enrolment.student_account_name == stu)\
    #     .group_by(Enrolment.id, Enrolment.enrolment_number, Enrolment.census_date)\
    #     .order_by(desc(Enrolment.census_date)).all()
    # Note, enrolment_number is not a unique index for this table  # ToDo: Need to group_by(intake_number)?
    flash(u'Possible enrolments: ' + str(poss_enrs))  # dbg
    for enr in poss_enrs:  # Check referral source
        email = enr.student_person_account_email    # [4]
        phone = enr.student_person_account_mobile   # [3]
        source = enr.referral_source                 # [5]
        flash(u'source: ' + str(source) + u' | broker: ' + str(broker))  # dbg
        if source == broker:   # ToDo:  Should we do...  like *broker*
            if email == eml or phone == pho or (email == '' and phone == ''):
                qual_upper = enr.qualification_name.upper()   # [12]   # Compare course titles in ALL CAPS
                # poss_enrs.append(enr)
                if qual_upper != title_all_upper:
                    results['status'] = 'No Match Found'
                    return results
                else:
                    pass  # Then still possible ...
        else:  # source != broker:
            # results['payable'] = False  # Should still be False from initialization above.
            results['status'] = 'Not Your Student'
            return results  # Can also occur because of CASIS data entry error ie.  an enrolment was created without
            # linking to a broker as the referral source. However in this case, the feedback in status is the same.

    # round2 = casis_get('Form', 'student_name', "'"+stu+"'")
    poss_forms = Form.query.filter(Form.student_name == stu).all()
    for form in poss_forms:
        email = form.student_email
        phone = form.student_mobile_number
        source = form.referral_source
        if source == broker:
            if email == eml or phone == pho or (email == '' and phone == ''):
                qual_upper = form.parent_qualificationstr.upper()
                # poss_forms.append(form)
                if qual_upper != title_all_upper:
                    results['status'] = 'No Match Found'
                    return results
                else:
                    pass  # Then still possible ...
        else:
            results['status'] = 'Not Your Student'
            return results

    # round3 = casis_get('Opportunity', 'account_name', "'"+stu+"'")
    poss_opps = Opportunity.query.filter(Opportunity.account_name == stu).all()
    # ToDo:  may also need to check for tags in opportunity_name
    # Sort round3 by created_date,
    for opp in poss_opps:
        email = opp.contact_email
        phone = opp.phone
        source = opp.opportunity_name
        if source == broker:
            if email == eml or phone == pho or (email == '' and phone == ''):
                qual_upper = opp.course_name.upper()
                # poss_opps.append(opp)
                if qual_upper != title_all_upper:
                    results['status'] = 'No Match Found'
                    return results
                else:
                    pass  # Then still possible ...
        else:
            results['status'] = 'Not Your Student'
            return results

    # poss_enrs ~ [(enr_num, stu_ac_name, sac_mobile, sac_email, ref_src, formNo,,,
    #               qualification_name, delivery, census, title_all_upper)]           # Need intake_number also?

    if poss_enrs:

        # ToDo: depending if it's a double degree and which census date...
        # double degree <= multiple enr_nums with status 'Active' and both titles are in list of doubles
        # OR, they could have done a course before, in which case we want the most recent.

        # Look for the enrolment_number where start_date is most recent, it already ordered by census_date
        # poss_enrs.sort(key=lambda t: t[16])  # [16] is ['census_date']
        # If dealing with tuples at this point...
        # poss_row = poss_enrs.sort(key=lambda t: t[8])  # [8] is ['enrolment_start_date']

        poss_row = Enrolment.query.filter(Enrolment.student_account_name == stu)\
            .group_by(Enrolment.id, Enrolment.enrolment_number, Enrolment.census_date, Enrolment.enrolment_start_date)\
            .order_by(desc(Enrolment.census_date), desc(Enrolment.enrolment_start_date)).first()
        # Re-querying here but what the hey.
        # ToDo: Need to group_by(intake_number) ???
        if not poss_row:
            results['status'] = 'No Match Found'
            results['payable'] = False
            return results  # If we can't find an enrolment start date, the answer is No! Nada! Nothing!
        # else carry on...

        # Verify the claim's stage param against poss1['enrolment_status'] by converting stage into a date.
        # Need to count thru to gen cancel date and census date.  stage = census1 => first census date etc.
        i = stage_enum.index(stage) - 1  # ie. Counting from 0, skipping first two, gives the i'th census in the enum
        flash(u'That is the Census number: ' + str(i))

        if len(poss_enrs) >= i:  # Here 'i' is the census num of the stage being claimed
            results['payable'] = True
            census_date = poss_row.census_date  # Is this the same as poss_enrs[i][14]?  # ['census_date']
        else:  # The number of census dates is less than the census number claimed in var 'stage'
            results['payable'] = False
            census_date = None

        enr_status = poss_row.enrolment_status  # [7] == ['enrolment_status'] can also be 'Active([Re]Commencement)' etc.
        # Need to check dates as may still be payable if cancelled after already passed census
        today = datetime.utcnow().date()
        if enr_status in ['Active(Commencement)', 'Active (Commencement)', 'Active(Recommencement)',
                          'Active (Recommencement)', 'Active (Re-commencement)', 'Active(Re-commencement)']:
            results['status'] = 'Active'  # We're not sure what can come out of CASIS but we'll accept all the above
            if census_date and today > census_date:
                results['payable'] = True
                results['census_date'] = census_date
        elif enr_status in ['Cancelled', 'cancelled', 'CANCELLED']:
            results['status'] = 'Cancelled'
            cancel_date = poss_row.cancellation_date
            results['census_date'] = census_date
            if cancel_date and census_date:
                if cancel_date > census_date:
                    results['payable'] = True
            else:
                results['payable'] = False
        results['delivery'] = poss_row.delivery_mode
        results['location'] = poss_row.campus_name

    elif poss_forms:
        # NOT PAYABLE because there's no enrolment
        flash(u'poss2: ' + str(poss_forms))  # dbg
        results['status'] = 'Has Not Enrolled'
        results['payable'] = False
        results['census_date'] = None

    elif poss_opps:  # Should be ordered by created_date
        # NOT PAYABLE because there's no enrolment but we still want to give feedback
        # If pri_campaign_src != broker then not your student else check if not interested

        # select primary_campaign_source from Opportunity
        # where account_name = stu  # ToDo or opportunity_name like ...?
        earliest_pri_camp_src = Opportunity.query.filter(Opportunity.account_name == stu)\
            .order_by(desc(Opportunity.created_date)).first().primary_campaign_source

        # If there is another broker with earlier created_date, they get it.
        if earliest_pri_camp_src != broker:
            results["status"] = 'Not Your Student'
            results['payable'] = False
            results['census_date'] = None
            results['delivery'] = None
            results['location'] = None  # Because we don't want to tell them nothin!

        for obj in poss_opps:
            if 'Not Interested' in obj.enrolment_stage:
                results['status'] = 'Did Not Enrol'
                results['payable'] = False
            else:
                results['status'] = 'Has Not Enrolled'
                results['payable'] = False
                results['delivery'] = obj.delivery_type

    flash(u'RESULTS: ' + 'status ' + str(results['status']) + '|'
          + 'payable ' + str(results['payable']) + '|'
          + 'census_date ' + str(results['census_date']) + '|'
          + 'delivery ' + str(results['delivery']) + '|'
          + 'location ' + str(results['location']) + '|'
          )
    return results


'''
def unique_everseen(iterable, key=None):  # from python docs itertools recipes -> dedup()
    """ List unique elements, preserving order. Remember all elements ever seen."""
    # unique_everseen('AAAABBBCCDAABBB') --> A B C D
    # unique_everseen('ABBCcAD', str.lower) --> A B C D
    seen = set()
    seen_add = seen.add
    if key is None:
        for element in ifilterfalse(seen.__contains__, iterable):
            seen_add(element)
            yield element
    else:
        for element in iterable:  # in our case, for row in possibles1
            k = key(element)     # key(row) == row[0]
            if k not in seen:
                seen_add(k)    # seen is a set of keys
                yield element  # element yielded of basis of key in seen
'''


def casis_get(tbl, col, val):  # CASIS lookup -- returns a list of rows for tbl
    # Currently, there is only one CASIS report mirroring CASIS data for us
    if tbl == 'Enrolment':
        # Enrolment.query.filter('enrolment.c.'+col == val)
        sql = text("select * from Enrolment where " + col + " = " + val)
    elif tbl == 'Form':
        # Form.query.filter('form.c.'+col == val)
        sql = text("select * from Form where " + col + " = " + val)
    elif tbl == 'Opportunity':
        # Opportunity.query.filter('opportunity.c.'+col == val)
        sql = text("select * from Opportunity where " + col + " = " + val +
                   "order by created_date")
    elif tbl == 'Possibles1':
        result = Possibles3.query.filter(col == val).fetchall()
        return result
    else:
        return False
    conn = db.engine.connect()
    result = conn.execute(sql).fetchall()
    return result


def calc_amt_rcti(this_rcti):
    # The queries here are basically copied from the render rcti fn. Can't see right now any easy way of
    # avoiding duplication of the queries. We need to calc the commission on each claim and store it in
    # the DB for the business process of forwarding claim#'s and their $ amounts to Accounts Payable for
    # approval and processing.
    the_claim = (Rcti.query.filter(Rcti.id == this_rcti).scalar()).claim_id  # .scalar? There can be only one!
    the_user = (Claim.query.filter(Claim.id == the_claim).scalar()).user_id
    the_broker = (User.query.filter(User.id == the_user).scalar()).broker_id

    # Now choose MOU with the most recent effective date (assuming no one puts in future dated MOU's!
    the_mou = MOU.query.join(agreed, MOU.id == agreed.c.mou_id)\
        .join(Broker, Broker.id == agreed.c.broker_id)\
        .filter(Broker.id == the_broker)\
        .order_by(desc(MOU.effective)).first().id  # Assuming chronological order, last is most recent.
    #ToDo can't pick just one style for all recs in a claim.
    contract_style = MOU.query.filter(MOU.id == the_mou).scalar().style
    #ToDo: Should define a constant like GST_RATE instead of hardcoding 10% as 1.10
    if contract_style == 'flat_fee':
        items_flat = text("select flat_fees.fee * 1.10 as gst_incl_flat"
                          + "  from student, course, course_types, progress, claimed, payable, rcti, mou, flat_fees "
                          + " where student.student_id = progress.student_id "
                          + "   and course.course_code = progress.course_code "
                          + "   and progress.progress_id = payable.progress_id "
                          + "   and claimed.progress_id = progress.progress_id "
                          + "   and claimed.census_date < now()::date "
                          + "   and payable.rcti_id = rcti.rcti_id "
                          + "   and payable.rcti_id =  :rcti "
                          + "   and mou.mou_id = :mou "
                          + "   and course_types.mou_id = mou.mou_id "
                          + "   and course_types.course_code = course.course_code "
                          + "   and flat_fees.course_type = course_types.category "
                          + "   and flat_fees.mou_id = mou.mou_id "
                          + "   and flat_fees.delivery = progress.delivery "
                          + "   -- and flat_fees.stage = progress.stage "
                          + "   and flat_fees.max = 999999 "
                          + "   and flat_fees.min = 0 "
                          )   # + "join enrolment on enrolment.student_account_name = student.name "
                             # joining on enrolment stuffs things up because it's de-normalised and has duplicates
    elif contract_style == 'pct_gross':
        items_gross = text("select percent_gross.percent * course_fees.fee * 1.10 as gst_incl_gross"
                         + "from student, course, progress, payable, mou, rcti, "
                         + "     course_fees, course_types, claimed, location, percent_gross "
                         + "where student.student_id = progress.student_id "
                         + "   and course.course_code = progress.course_code "
                         + "   and payable.progress_id = progress.progress_id "
                         + "   and claimed.progress_id = progress.progress_id "
                         + "   and claimed.census_date < now()::date "
                         + "   and payable.rcti_id = rcti.rcti_id "
                         + "   and payable.rcti_id =  :rcti "
                         + "   and mou.mou_id = :mou "
                         + "   and course_fees.course_code = course.course_code "
                         + "   and course_fees.location_id = location.location_id "
                         + "   and course_types.course_code = course.course_code "
                         + "   and course_types.mou_id = mou.mou_id "
                         + "   and percent_gross.course_type = course_types.category "
                         + "   and percent_gross.delivery = progress.delivery "
                         + "   and percent_gross.stage = progress.stage "
                         + "   and percent_gross.min < course_fees.fee "
                         + "   and course_fees.fee < percent_gross.max "
                         )   # + "join enrolment on enrolment.student_account_name = student.name "
                             # joining on enrolment stuffs things up because it's de-normalised and has duplicates
    elif contract_style == 'pct_stage':
        items_stage = text("select SUM(percent_stage.percent * course_fees.fee) * 1.10 "
                         + "from student, course, progress, payable, mou, rcti, "
                         + "     course_fees, course_types, claimed, location, percent_stage "
                         + "   and course.course_code = progress.course_code "
                         + "   and payable.progress_id = progress.progress_id "
                         + "   and payable.rcti_id =  :rcti "
                         + "   and mou.mou_id = :mou "
                         + "   and course_fees.course_code = course.course_code "
                         + "   and course_fees.location_id = location.location_id "
                         + "   and course_types.course_code = course.course_code "
                         + "   and course_types.mou_id = mou.mou_id "
                         + "   and percent_stage.course_type = course_types.category "
                         + "   and percent_stage.delivery = progress.delivery "
                         + "   and percent_stage.stage = progress.stage "
                         + "   and percent_stage.min < course_fees.fee "
                         + "   and course_fees.fee < percent_stage.max "
                         )
    else:  # Something's gone wrong.
        # Add some error trapping here. Redirect to generic error page?
        flash(u'Something has gone wrong! This Rcti seems to have no MOU associated with it.')
        pass
    # Now execute whichever query we chose, to get the line items for the Rcti and calc totals
    conn = db.engine.connect()

    payables = conn.execute(items_flat, rcti=this_rcti, mou=the_mou).fetchall()
    total = map(sum, payables)
    flash(u'This RCTI has payable items: ' + str(payables))  # dbg

    # ######## Use total to update the Rcti with amount  ################
    if payables:
        #Rcti.query.get(this_rcti).amount = total_payable  # Could we just do this to update? No, gets ResultProxy.
        db.session.query(Rcti).filter_by(id=this_rcti).update({"amount": total})
        db.session.commit()
        flash(u'The Total Payable is: ' + str(total))  # dbg
    else:
        flash(u'This RCTI has a zero amount payable!')


@app.route('/view_courses', methods=['GET'])
def view_courses():
    course_recs = Course.query.all()
    return render_template('view_courses.html', courses=course_recs)  # {{ student.email }} etc.


@app.route('/update_mou', methods=['GET', 'POST'])
# @login_required  # Still get "Please login ..." msg even after logging in
def update_mou():
    if request.method == 'POST':
        if not request.form['mou_id']:
            flash('An MOU ID is required', 'error')
        #ToDo: Check current g.user in {Admin}
        #when_paid = request.form['when_paid']
        if request.form['style'] == 'flat_fee':
            flat_fees = FlatFees(request.form['mou_id'],
                                 request.form['delivery'],
                                 request.form['course_type'],
                                 request.form['bracket'],
                                 request.form['fee']
                                 )
            db.session.add()
            db.session.commit(flat_fees)
        elif request.form['style'] == 'pct_gross':
            percent_gross = PercentGross(request.form['mou_id'],
                                         request.form['delivery'],
                                         request.form['course_type'],
                                         request.form['bracket'],
                                         request.form['stage'],
                                         request.form['percent_gross']
                                         )
            db.session.add(percent_gross)
            db.session.commit()
        elif request.form['style'] == 'pct_stage':
            percent_stage = PercentStage(request.form['mou_id'],
                                         request.form['delivery'],
                                         request.form['course_type'],
                                         request.form['stage'],
                                         request.form['percent_stage']
                                         )
            db.session.add(percent_stage)
            db.session.commit()
        flash(u'Entry of MOU payment point was successful.')
        return redirect(url_for('update_mou'))

    return render_template('mou_details.html')


def casis_check(table, col, datum):
    '''
    sf = Salesforce(username='gavin.munro@careersaustralia.edu.au.staging', password='0gmandino',
                    security_token='9p4WmOqHQwwCgWS0pjZXhTwq', sandbox=True)
    recs = sf.query("SELECT qualification_name from enrolment ...")
    '''
    # The SimpleSalesforce security token login is not working
    # If there is a proxy, we may need to use the instance/session id method below
    # I believe cs5 is our current staging instance
    '''
    proxies = {"http": "http://10.10.1.10:3128",
               "https": "http://10.10.1.10:1080",
               }
    sf = Salesforce(instance='cs5.salesforce.com', session_id='', proxies=proxies)
    '''
    return True


@app.route('/upload_po_nums', methods=['GET', 'POST'])
def upload_po_nums():
    # accounts_personnel = ["Leticia", "Roman", "AP_user"]
    # if g.user not in accounts_personnel:
    #     flash(u'You do NOT have permission to access this page!')
    #     return render_template('index.html')
    # else:
    user_in = 3 # dbg #ToDo Remove hardcoding of logged in user
    if False:
        pass
    else:
        if request.method == 'GET':

            return render_template('upload_po_nums.html', user_in=user_in)
        else:  # method == 'POST'
            csv_file = request.files['csv_file']  # form dict
            if not(csv_file and allowed_file(csv_file.filename)):   # ie. a .csv file
                flash(u'This is not a valid filename for a CSV file.')
            else:
                filename = secure_filename(csv_file.filename)
                csv_path = os.path.join(os.environ['OPENSHIFT_DATA_DIR'], '/admin')
                csv_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)   # dbg #ToDo This sends to /tmp for dbg!
                csv_file.save(csv_path)
                with open(csv_path, "rb") as file_obj:
                    reader = csv.DictReader(file_obj, delimiter=",")
                    for row in reader:
                        # data row template
                        # ["Broker", "RCTI#", "PO#", "Amount"]
                        broker = Broker.query(filter(Broker.orgname == row["Broker"]))
                        rcti = Rcti.get(row["RCTI#"])
                        # Now for a sanity check that this rcti is for a claim by this broker
                        if Claim.get(rcti.claim_id).user_id not in Broker.users:
                            flash(u'ERROR IN CSV FILE! Broker ' + broker.name + u'did not claim for RCTI#' + rcti.id)
                            flash(u'THE FILE HAS NOT BEEN PROCESSED')
                            return render_template('upload_po_nums.html')
                        po = row["PO#"]
                        amount = row["Amount"]
                        date = datetime.utcnow()
                        rcti.po_num = po
                        rcti.amount = amount
                        rcti.processed = date
                        # This is not necessary. SQLA has no update() db.session.update(rcti)
                # file closed by with stmt
                db.session.commit()  # Hope the session will hold all updates. Want to reject whole file if 1 row wrong.
            flash(u'The file has been processed successfully.')
            return render_template('upload_po_nums.html', user_in=user_in)


@app.route('/student_status', methods=['GET'])
def student_status():
    # Brokers should only be able to query on "their" students, so only for...
    # those they've claimed and which are "payable" ie. claimed and matched
    # select * from progress, paid ?
    return render_template('student_status.html')


@app.route('/claim_history', methods=['GET'])
def claim_history():
    # Allow users to download a CSV file of their claims history
    flash(u'Claim history for user: ', current_user)
    fname = str(Broker.get(User.get(current_user).broker_id).orgname + u'_claims')
    # Using query from claims method
    sql_str = text("select cl.claim_id, filename, upload_date, "
                   + "  (select count(*) from claimed "
                   + "   where claimed.claim_id = cl.claim_id) as count, "
                   + "  (select count(*) from payable, claimed, rcti "
                   + "   where payable.progress_id = claimed.progress_id "
                   + "   and claimed.claim_id = cl.claim_id "
                   + "   and rcti.rcti_id = payable.rcti_id "
                   + "   and rcti.claim_id = cl.claim_id "
                   + "   and cl.user_id = :user) as referrals, "
                   + "rcti_id, po_num, processed, amount "
                   + "from claim cl left join rcti "
                   + "on rcti.claim_id = cl.claim_id "
                   + "where cl.user_id = :user ")
    conn = db.engine.connect()
    # current_user is a Flask login var
    claims_recs = conn.execute(sql_str, user=current_user.id).fetchall()
    return redirect(export_csv(claims_recs, fname))


def export_csv(qry_result, fname):  # SA return type for queries is list of tuple-like proxy objects
    # Create a file using the csv library.
    # Where will file be saved? (app.config['UPLOAD_FOLDER']
    fname = fname + (datetime.utcnow()).ToString()  # Append timestamp to make file names unique
    filename = secure_filename(fname)
    with open(filename, 'wb') as fobject:
        writer = csv.writer(fobject, dialect='excel', delimiter=',', quotechar='"')
        for row in qry_result:
            writer.writerow(row)
            # Do I need to know how many cols there are? I don't think so.
    #fobject.close() auto done by with stmt
    fobject.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    link = url_for('/downloads/'+'filename')
    return link


def paste_special(some_rcti):
    '''
    This fn is to gen a block of cells (as a CSV format file) that can be pasted
    into "TechOne" which is a Queensland Govt preferred .NET application that is
    used by Accounts Payable to manage all financial transactions for the company.
    As it's a .NET app they can use "Rt. Click > Paste Special" to insert all the
    required special codes in the right places to automate this business process.
    '''
    # eg. cell_block = [
    #     [11644.01,,test test test,NEILT,N,,,1904,,,BrokerPay Ref],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ],
    #     [Non Stock,test test test,S,C,1100,,,,QL,BSB50207.500001.720.76001, ]
    #     ]

    rcid = some_rcti.id
    sacn = '11644.01'

    header = {
        "Supplier Account Number": sacn,
        "Blank Col 1": '',
        "PR Comment": 'BrokerPay generated',
        "Initiator of PO": 'NEILT',
        "Constant 1": 'N',
        "Blank Col 2": '',
        "Blank Col 3": '',
        "Constant 2": 1904,
        "Default due date": '',
        "Blank Col 4": '',
        "Reference": 'Rcti-' + rcid
    }
    #qry = text("select student_id from student, progress, payable where ...")
    students = Student.query.join(Progress, Student.id == Progress.student_id)\
        .join(Progress, Progress.id == Payable.progress_id)\
        .join(Payable, Payable.rcti_id == rcid)\

    rcti = Rcti.get(rcid)
    price = rcti.amount  #ToDo   OR is this the price _per student_ in the RCTI?
    #ToDo  with open file blah.blah
    #ToDo write header to this file
    payable_progressions = Payable.query.filter(Payable.rcti_id == rcid)
    for p in payable_progressions:
        student = Student.get(p.student_id)
        course = p.course_code
        stu_taking_course = Taking.query.filter(Taking.student_id == student and Taking.course_code == course)\
            .scalar()   # There shall be only one!
        vfh_contract = stu_taking_course.contract_code
        tech1_contract = stu_taking_course.tech1_contract
        acn = course + '.' + vfh_contract + '.' + tech1_contract   # tech1_contract = '76001'?
        # ToDo: Check this is where '.76001' comes from
        coding = {
            "Constant 1": 'Non Stock',
            "Student name": student.name,
            "Constant 2": 'S',
            "Constant 3": 'C',
            "Comm inc GST": price,
            "Blank Col 1": '',
            "Blank Col 2": '',
            "Blank Col 3": '',
            "Ledger code": 'QL',
            "Account number": acn,
            "Blank Col 4": 'Rcti-' + rcid
        }
        #ToDo write this line to file
    # File closed by with
    #ToDo send the file off somwhere


def fill_pdf(fields, data, rcti):
    # data = ? One row for each PDF?
    output_folder = os.path.join(os.environ['OPENSHIFT_TMP_DIR'], '/rcti_out')
    # path.insert(0, os.getcwd())  # Not sure about this script path stuff!
    # path.insert(1, os.getcwd())  # This stuff should be handled by virtualenv
    filename_prefix = "Rcti-"
    pdf_template = "Rcti-ATO.pdf"
    pdf_file = filename_prefix + "00" + rcti.rcti_id.toString()
    tmp_file = "tmp.fdf"
    # constants for Careers Australia details
    ca_name = "Careers Austrllia Group Limited"
    ca_address = "108 Wickham Street"
    ca_suburb = "Fortitude Valley"
    ca_postcode = "4006"
    ca_ABN = "52 122 171 840"
    # Get supplier details for inclusion on invoice
    b = User.query(filter(User.user_id == current_user)).broker_id
    supplier = Broker.query.filter_by(Broker.broker_id == b)
    name = supplier.orgname
    address = supplier.addrress
    suburb = supplier.suburb
    postcode = supplier.postcode
    abn = supplier.abn
    # "select * from payable where rcti_id = rcti group by stage_id"
    # headers: SupplierName, Address, Suburb, State, Postcode, ABN, Amount

    # line-items: Desc, Value, GST, Price
    # Desc == Student.name, progress.course_code, stages.stage
    # Value == Rcti.amount
    # GST == 0.10 * Value
    # Price =  Value + GST
    line_items = Payable.query(filter(Payable.rcti == rcti)).\
        join(Progress, Progress.id == Payable.progress_id).\
        join(Student, Student.id == Progress.student_id)


    fdf = forge_fdf("", fields, [], [], [])
    fdf_file = open(tmp_file, "w")
    fdf_file.write(fdf)
    fdf_file.close()

    output_file = '{0}{1} {2}.pdf'.\
        format(output_folder, filename_prefix, fields[1][1])
    cmd = 'pdftk "{0}" fill_form "{1}" output "{2}" dont_ask'.\
        format(pdf_file, tmp_file, output_file)

    os.system(cmd)
    os.remove(tmp_file)
    '''
    for row in data:
        if row[0][1] == 'Yes':
            continue
        # print('{0} {1} created...'.format(filename_prefix, i[1][1]))
        fill_pdf(row)
    '''


if __name__ == '__main__':
    app.run()
