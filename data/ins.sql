SET DATESTYLE = 'ISO, DMY';

INSERT INTO broker
(broker_id, orgname, address, suburb, state, postcode, abn) 
VALUES 
(1, 'I Want A Winnebago', '25 Rose Lane', 'Toledo', 'QLD', 4321, '24 555 989 567'),
(2, 'Equine Education', '16 Riding Road', 'Deep Forest', 'VIC', 2345, '16 007 369 440'),
(3, 'Wahoo Acquisitions', '4 Marine Parade', 'Sunken Island', 'QLD', 4206, '17 300 459 221')
;

INSERT INTO mou
(mou_id, title, filename, effective, style, when_paid)
VALUES 
(1, 'Desirerrata', 'NemosMemo.docx', '2011-04-12', 'flat_fee', 'at 2 weeks'),
(2, 'Hungry Horses', 'TheHerdMOU-R2_2134532.docx', '2010-06-24', 'pct_gross', null),
(3, 'Wahoo Serious', 'Shimano_Reel-2.3.docx', '2013-03-12', 'pct_stage', null)
;

INSERT INTO agreed
(broker_id, mou_id)
VALUES 
(1, 1),
(3, 3),
(2, 2)
;

INSERT INTO percent_stage
(mou_id, delivery, course_type, stage, percent)
VALUES
(3, 'Campus', 'Dip', 'Census1', 25),
(3, 'Campus', 'Dbl', 'Census1', 25),
(3, 'Campus', 'Triple Dip Bus Mgt, HR & Logistics', 'Census1', 25),
(3, 'Campus', 'Dip', 'Census2', 25),
(3, 'Campus', 'Dbl', 'Census2', 25),
(3, 'Campus', 'Triple Dip Bus Mgt, HR & Logistics', 'Census2', 25)
;

INSERT INTO percent_gross
(mou_id, delivery, course_type, stage, min, max, percent)
VALUES
(2, 'Campus', 'Dip', 'Census1', 0, 999999, 0.10),
(2, 'Campus', 'Dip', 'Census2', 0, 999999, 0.10),
(2, 'Campus', 'Nursing', 'Census2', 0, 999999, 0.125),
(2, 'Campus', 'Nursing', 'Census4', 0, 999999, 0.125),
(2, 'Campus', 'Cert', 'Commencement', 0, 999999, 0.10),
(2, 'Campus', 'Cert', 'Census1', 0, 999999, 0.10)
;

INSERT INTO flat_fees
(mou_id, delivery, course_type, stage, min, max, fee)
VALUES
(1, 'Campus', 'Cert', 'Commencement', 0, 999999, 400),
(2, 'Campus', 'Cert', 'Commencement', 0, 999999, 250.00),
(2, 'Online', 'Dip', 'Census1', 0, 999999, 350.00)
;

INSERT INTO course
(course_code, title)
VALUES
('Test0', 'COURSE TITLE NOT FOUND'),
('Test1', 'CERTIFICATE III IN CARPENTRY'),
('Test2', 'CERTIFICATE IV IN WARG RIDING'),
('Test3', 'CERTIFICATE IV IN DATA MANAGEMENT'),
('BSB50207', 'DIPLOMA OF BUSINESS'),
('BSB50407', 'DIPLOMA OF BUSINESS ADMINISTRATION'),
('BSB50613', 'DIPLOMA OF HUMAN RESOURCES MANAGEMENT'),
('BSB51107', 'DIPLOMA OF MANAGEMENT'),
('BSB51207', 'DIPLOMA OF MARKETING'),
('BSB51413', 'DIPLOMA OF PROJECT MANAGEMENT'),
('CHC50113', 'DIPLOMA OF EARLY CHILDHOOD EDUCATION AND CARE'),
('CHC51712', 'DIPLOMA OF COUNSELLING'),
('CPC50210', 'DIPLOMA OF BUILDING AND CONSTRUCTION'),
('FNS50210', 'DIPLOMA OF ACCOUNTING'),
('HLT51612', 'DIPLOMA OF NURSING (ENROLLED-DIVISION 2 NURSING)'),
('MEM50105', 'DIPLOMA OF ENGINEERING'),
('TLI50410', 'DIPLOMA OF LOGISTICS'),
('CHC50612', 'DIPLOMA OF COMMUNITY SERVICES WORK'),
('BSB50207_BSB50613', 'DOUBLE DIPLOMA OF BUSINESS & HUMAN RESOURCES MANAGEMENT'),
('BSB50207_BSB51107', 'DOUBLE DIPLOMA OF BUSINESS & MANAGEMENT'),
('CHC51712_CHC50612', 'DOUBLE DIPLOMA OF COUNSELLING & COMMUNITY SERVICES WORK')
;

INSERT INTO course_types
(course_code, mou_id, category)
VALUES
('Test0', 2, 'Nursing'),
('Test1', 2, 'Cert')
;

INSERT INTO location
(location_id, tech1_code, location)
VALUES
(1,  310, 'Adelaide'),
(2,  120, 'Bowen Hills'),
(3,  142, 'Burleigh'),
(4,  135, 'Caboolture'),
(5,  110, 'Fortitude Valley'),
(6,  320, 'Hindmarsh'),
(7,  410, 'Melbourne'),
(8,  140, 'Nerang'),
(9,  210, 'Newcastle'),
(10, 216, 'Parramatta'),
(11, 510, 'Perth'),
(12, 150, 'Salisbury'),
(13, 145, 'Southport'),
(14, 220, 'Sydney'),
(15, 160, 'Toowoomba'),
(16, 170, 'Townsville'),
(17, 720, 'Online'),
(18,  27, 'Gotham Place'),
(19,  36, 'Boeing Hills')
;

INSERT INTO users 
(user_id, email, password, registered_on, broker_id) 
VALUES 
(1, 'bruce.lee@martial.com.au', 'ca', '2014-11-28 05:17:46.362000', 1),
(2, 'sparky.andrews@electrical.com.au', 'ca', '2014-11-28 05:17:46.362000', 2),
(3, 'galik.romanov@russky.com.au', 'ca', '2014-11-28 05:17:46.362000', 3),
(4, 'bunty.samuels@mathematica.com.au', 'ca', '2014-11-28 05:17:46.362000', 1),
(5, 'gavin.munro@pythonista.com.au', 'ca', '2014-11-28 05:17:46.362000', 2)
;

INSERT INTO student 
(student_id, name, email, phone)
VALUES
(1001, 'Jessica Grund', 'jessica.grund@mail.com', '0461870867'),
(1002, 'Glinda Souders', 'glinda.souders@mail.com', '0461870867'),
(1003, 'Dia Gilbert', 'dia.glibert@gmail.com', '0461870867'),
(1004, 'Jeremy Kennamer', 'jeremy.kennamer@mail.com', '0461870867')
;

INSERT INTO claim 
(claim_id, filename, upload_date, user_id) 
VALUES
(1001, 'TestClaim0.csv', '2015-04-18', 1),
(1002, 'Claim-TheHerd-2015.01.15.csv', '2015-01-15', 2)
;

INSERT INTO progress
(progress_id, student_id, course_code, stage, delivery, location_id)
VALUES
(10001, 1001, 'Test1', 'Commencement', 'Campus', 1),
(10002, 1001, 'Test1', 'Census1', 'Campus', 1),
(10003, 1002, 'Test2', 'Census2', 'Campus', 2)
;

INSERT INTO taking
(taking_id, student_id, course_code, contract_code, tech1_contract)
VALUES
(1001, 1001, 'Test1', 'B27/36', '500001'),
(1002, 1002, 'Test2', 'B27/36', '500001'),
(1003, 1003, 'Test3', 'B27/36', '500001')
;

INSERT INTO claimed
(claim_id, progress_id, status, payable, census_date)
VALUES
(1001, 10001, null, False, null),
(1002, 10001, 'Active', True, '28/06/2015'),
(1002, 10002, null, False, null),
(1001, 10003, null, False, null)
;

INSERT INTO rcti
(rcti_id, po_num, processed, amount, claim_id)
VALUES
(101, 'PO# 1767458-1', '2015.01.19', 2040, 1002),
(102, 'PO# 4356828-0', '2015.02.01', 250, 1001)
;

INSERT INTO payable
(progress_id, rcti_id)
VALUES
(10001, 101),
(10002, 102)
;

INSERT INTO enrolment
    (enrolment_id, enrolment_number, 
    student_account_name, student_person_account_mobile, student_person_account_email,
    referral_source, form_number, enrolment_status, enrolment_start_date, cancellation_date,
    cancellation_reason, contract_code, campus_name, qualification_name, delivery_mode, census_date, 
    qualification_course_id)
VALUES
(1, '1001382', 
	'Jessica Grund', '0461870867', 'jessica.grund@mail.com', 
    'Equine Education', 'Fno.13616' ,'Active', '2015-01-1', null, 
    '', 'VFH0000023', 'Bowen Hills', 'Cert III in Carpentry', 'Campus', '2015-01-1', 
    'BSB-13671'),
(2, '10034572', 
	'Jessica Grund', '0461870867', 'jessica.grund@mail.com', 
    'Equine Education', 'Fno.13616' ,'Active', '2015-01-1', null, 
    '', 'VFH0000023', 'Bowen Hills', 'Cert IV Forestry Mangement', 'Campus', '2015-02-2', 
    'BSB-13461'),
(3,'EN0000247339','Ashish Pyklie','0442 676 331','ashpykel@yahoo.com','NTD (National Training & Development)',null,'Cancelled','13-01-2015','16-01-2015','Deferring to another intake','VFH00000','Adelaide Campus','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(4,'EN0000246562','Chaya Shartai','0421 995 608','chaya83.it@gmail.com','NTD (National Training & Development)',null,'Cancelled','19-01-2015','5-02-2015','Deferring to another intake','VFH00001','Adelaide Campus','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(5,'EN0000246562','Chaya Shartai','0421 995 608','chaya83.it@gmail.com','NTD (National Training & Development)',null,'Cancelled','19-01-2015','5-02-2015','Deferring to another intake','VFH00002','Adelaide Campus','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(6,'EN0000181276','Chloe Bold','0421 214 417','chloe_1993@hotmail.com','NTD (National Training & Development)',null,'Cancelled','19-01-2015','29-01-2015','Personal and health reasons','VFH00003','Adelaide Campus','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(7,'EN0000247327','Elizabeth SanPedro','0448 561 387','lizpedro74@gmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Southport','Diploma of Marketing','Classroom Based','9-02-2015',null),
(8,'EN0000247327','Elizabeth SanPedro','0448 561 387','lizpedro74@gmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Southport','Diploma of Marketing','Classroom Based','18-04-2016',null),
(9,'EN0000235302','Jacqueline Ghanmon','0410 290 111','stelmo_is_4@hotmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Melbourne','Diploma of Accounting','Classroom Based','9-02-2015',null),
(10,'EN0000259381','Jessica Mann','0420 569 762','jessica.mann@hotmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Southport','Diploma of Marketing','Classroom Based','9-02-2015',null),
(11,'EN0000259381','Jessica Mann','0420 569 762','jessica.mann@hotmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Southport','Diploma of Marketing','Classroom Based','18-04-2016',null),
(12,'EN0000233867','Joseph Fazzazi','0452 063 844','joseph.fazzazi@gmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Bowen Hills','Diploma of Management','Classroom Based','9-02-2015',null),
(13,'EN0000236357','Karen Mead','0422 337 598','karenmead53@yahoo.com.au','IWTC',null,'Cancelled','19-01-2015','11-02-2015','Deferring to another intake','VFH00003','Caboolture','Diploma of Marketing','Classroom Based',null,null),
(14,'EN0000235281','Kody Sirus','0448 342 567','kody_sires@hotmail.com','IWTC',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Caboolture','Diploma of Marketing','Classroom Based','9-02-2015',null),
(15,'EN0000235247','Regina Bateman','0421 532 998','regina.bateman@bigpond.com','ContactCentresAustralia',null,'Cancelled','12-01-2015','12-01-2015','Other','VFH00003','Fortitude Valley','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(16,'EN0000246998','Regina Bateman','0421 532 998','regina.bateman@bigpond.com','ContactCentresAustralia',null,'Cancelled','12-01-2015','12-01-2015','Other','VFH00003','Fortitude Valley','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(17,'EN0000246998','Regina Bateman','0421 532 998','regina.bateman@bigpond.com','ContactCentresAustralia',null,'Cancelled','12-01-2015','12-01-2015','Other','VFH00003','Fortitude Valley','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(18,'EN0000246998','Regina Bateman','0421 532 998','regina.bateman@bigpond.com','ContactCentresAustralia',null,'Cancelled','12-01-2015','12-01-2015','Other','VFH00003','Fortitude Valley','Diploma of Nursing (Enrolled-Division 2 Nursing)','Classroom Based',null,null),
(19,'EN0000233858','Rejina Zelda','0401 229 182','zelda_regina@yahoo.com','NTD (National Training & Development)',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Nerang','Diploma of Logistics','Classroom Based','9-02-2015',null),
(20,'EN0000233858','Rejina Zelda','0401 229 182','zelda_regina@yahoo.com','NTD (National Training & Development)',null,'Active (Commencement)','19-01-2015',null,null,'VFH00003','Nerang','Diploma of Logistics','Classroom Based','18-04-2016',null),
(21,'EN0000260760','Rusell Hamed','0435 742 061','s2_is_main@hotmail.com','Repeat Business',null,'Active (Recommencement)','19-01-2015',null,null,'VFH00003','Newcastle Campus','Diploma of Project Management','Classroom Based','20-05-2015',null),
(22,'EN0000260760','Rusell Hamed','0435 742 061','s2_is_main@hotmail.com','Repeat Business',null,'Active (Recommencement)','19-01-2015',null,null,'VFH00003','Newcastle Campus','Diploma of Project Management','Classroom Based','9-02-2015',null),
(23,'EN0000260760','Rusell Hamed','0435 742 061','s2_is_main@hotmail.com','Repeat Business',null,'Active (Recommencement)','19-01-2015',null,null,'VFH00003','Newcastle Campus','Diploma of Project Management','Classroom Based','18-04-2016',null)
;

INSERT INTO course_fees
(course_code, location_id, fee)
VALUES
('Test0', 19, 22000),
('Test1', 2, 20400),
('Test2', 19, 10000),
('Test3', 18, 12000),
('BSB51413',9,16500),
('BSB51413',16,16500),
('BSB51413',2,16500),
('BSB51413',15,16500),
('BSB51413',1,16500),
('BSB51413',7,16500),
('BSB51413',19,16500),
('BSB50407',19,15500),
('BSB50207_BSB50613',10,24111),
('BSB50207_BSB50613',15,24111),
('BSB50207_BSB50613',2,24111),
('BSB50207_BSB50613',3,24111),
('BSB50207_BSB50613',4,24111),
('BSB50207_BSB50613',12,24111),
('BSB50207_BSB50613',13,24111),
('BSB50207_BSB50613',16,24111),
('BSB50207_BSB50613',1,14000),
('BSB50207_BSB50613',7,24111),
('BSB50207_BSB50613',11,24111),
('BSB50207_BSB50613',19,24111),
('BSB51207',16,15500),
('BSB51207',15,15500),
('BSB51207',18,15500),
('BSB51207',4,15500),
('BSB51207',19,15500),
('FNS50210',7,10990),
('BSB50613',9,15500),
('BSB50613',16,15500),
('BSB50613',2,15500),
('BSB50613',4,15500),
('BSB50613',14,15500),
('BSB50613',15,15500),
('BSB50613',18,15500),
('BSB50613',1,9000),
('BSB50613',7,15500),
('BSB50613',12,15500),
('BSB50613',19,15500),
('BSB51107',16,15500),
('BSB51107',11,15500),
('BSB51107',2,15500),
('BSB51107',3,15500),
('BSB51107',4,15500),
('BSB51107',14,15500),
('BSB51107',15,15500),
('BSB51107',18,15500),
('BSB51107',6,9000),
('BSB51107',7,15500),
('BSB51107',12,15500),
('BSB51107',19,15500),
('BSB50207',9,15500),
('BSB50207',11,15500),
('BSB50207',16,15500),
('BSB50207',2,15500),
('BSB50207',3,15500),
('BSB50207',4,15500),
('BSB50207',14,15500),
('BSB50207',15,15500),
('BSB50207',18,15500),
('BSB50207',6,9000),
('BSB50207',7,15500),
('BSB50207',12,15500),
('BSB50207',19,15500),
('CHC51712_CHC50612',9,25000),
('CHC51712_CHC50612',11,25000),
('CHC51712_CHC50612',2,25000),
('CHC51712_CHC50612',4,25000),
('CHC51712_CHC50612',14,25000),
('CHC51712_CHC50612',15,25000),
('CHC51712_CHC50612',18,25000),
('CHC51712_CHC50612',6,18500),
('CHC51712_CHC50612',7,25000),
('CHC51712_CHC50612',12,25000),
('CHC51712_CHC50612',19,25000),
('CHC50612',9,16000),
('CHC50612',11,16000),
('CHC50612',2,16000),
('CHC50612',4,16000),
('CHC50612',14,16000),
('CHC50612',15,16000),
('CHC50612',18,16000),
('CHC50612',6,15000),
('CHC50612',7,16000),
('CHC50612',12,16000),
('BSB50207_BSB51107',16,23250),
('BSB50207_BSB51107',11,23250),
('BSB50207_BSB51107',2,23250),
('BSB50207_BSB51107',3,23250),
('BSB50207_BSB51107',4,23250),
('BSB50207_BSB51107',14,23250),
('BSB50207_BSB51107',15,23250),
('BSB50207_BSB51107',18,23250),
('BSB50207_BSB51107',6,13500),
('BSB50207_BSB51107',7,23250),
('BSB50207_BSB51107',12,23250),
('BSB50207_BSB51107',19,23250),
('CHC51712',9,13500),
('CHC51712',2,13500),
('CHC51712',4,13500),
('CHC51712',15,13500),
('CHC51712',18,13500),
('CHC51712',6,13500),
('CHC51712',7,13500),
('CHC51712',19,13500),
('CHC50113',2,9990),
('CHC50113',15,9990),
('CHC50113',6,9990),
('CHC50113',7,9990),
('CHC50113',12,9990),
('HLT51612',16,24750),
('HLT51612',5,24750),
('HLT51612',3,24750),
('HLT51612',1,17000),
('HLT51612',7,24750),
('TLI50410',18,21000),
('TLI50410',15,21000),
('TLI50410',14,21000),
('TLI50410',8,21000),
('TLI50410',4,21000),
('TLI50410',7,21000),
('TLI50410',3,21000),
('TLI50410',2,21000),
('TLI50410',19,21000),
('CPC50210',8,14000),
('CPC50210',14,14000),
('CPC50210',17,14000),
('CPC50210',7,14000),
('CPC50210',12,14000),
('MEM50105',2,22000),
('MEM50105',14,22000)
;
