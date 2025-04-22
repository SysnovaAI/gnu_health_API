Installation and Run :
cd middleware_api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
#uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
#new
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Doctor Registration
fetch all doctors
fetch single doctor
Patient Registration
fetch all patients
fetch single patients
fetch all users
JWT Token Generation
authentication and Login
token blacklisted Api
loged in user details api
make appointment
update appointment status


update profile
localhost:8000/api/doctor/1/update
{
  "full_name": "Dr. Ahsan Karim",
  "gender": "m",
  "phone_number": "017XXXXXXXX",
  "email": "ahsan@example.com",
  "username": "ahsan.karim",
  "year_of_experience": 8,
  "address_city": "Dhaka",
  "address_municipality": "Dhanmondi",
  "address_street": "Road 32",
  "address_street_number": "12A",
  "address_zip": "1209"
}
localhost:8000/api/patient/1/update
{
  "full_name": "Dr. Ahsan Karim",
  "gender": "m",
  "phone_number": "017XXXXXXXX",
  "email": "ahsan@example.com",
  "username": "ahsan.karim",
  "address_city": "Dhaka",
  "address_municipality": "Dhanmondi",
  "address_street": "Road 32",
  "address_street_number": "12A",
  "address_zip": "1209"
}



API Testing (Postman)
✅ GET /api/patient → Fetches all patients (is_patient = true).
✅ GET /api/doctor → Fetches all doctors (is_healthprof = true).
✅ GET /api/patients/3 → Fetches patient with ID 3 (is_patient = true).
✅ GET /api/doctors/5 → Fetches doctor with ID 5 (is_healthprof = true).
✅ GET /api/all-users → Fetches all users from party.



✅Doctor Registration : POST /api/doctor/register

Sample data : 
{
    "name": "Dr. Sanchita",
    "mobile_number": "01712345678",
    "email": "Sanchita@test.com",
    "password_hash": "Sanchita",
    "gender": "female",
    "year_of_experience": 10
}

✅Patient Registration : POST /api/patient/register

Sample data : 
{
    "name": "Dr. Sanchita",
    "mobile_number": "01712345678",
    "email": "Sanchita@test.com",
    "password_hash": "Sanchita",
    "gender": "female"
}

Login
✅ POST /auth/login → credentials (username = 'user_name_value' and password='password').
return :
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MSwibmFtZSI6IkFkbWluaXN0cmF0b3IiLCJsb2dpbiI6ImFkbWluIiwiZXhwIjoxNzQyNzE1NTcxfQ.NzH4y_olvTLd4FTK5otcNS_FYutgISLI9EGgmCgIRZg",
    "token_type": "bearer"
}

Loged In users Details
✅ GET /auth/me 
return :
{
    "user": {
        "id": 1,
        "name": "Administrator",
        "login": "admin",
        "exp": 1742796049
    }
}

Logout
✅ GET /auth/logout 
return :
{
    "message": "Successfully logged out"
}

Appointment Features :
1. Create Appointment (Only for logged-in users)

2. Get Appointment by ID (User can see only their own appointment)

3. Delete Appointment (Only the user who created it can delete it)

Make an Appointments:
✅ POST /api/appointments
Sample Input :
{
    "appointment_date": "2025-03-15 14:30:00",
    "appointment_type": "telemedicine",
    "healthprof": 2,
    "institution": 1,
    "speciality": 6,
    "state": "free",
    "urgency": "b",
    "visit_type": "followup"
}




Sample Output:
{
    "success": true,
    "appointment_id": 40,
    "appointment_name": "APP 2025/0c9cfb"
}
✅ POST /api/appointments_new
{
  "appointment_date": "2025-03-10 16:18:12",
  "healthprof": 1
}

Make an Appointments:
✅ PUT /api/appointments/41 {appointment_id}

Sample Input :
{
    "appointment_date": "2025-04-11 15:30:00",
    "state": "cancelled"
}

Sample Output:

{
    "success": true,
    "message": "Appointment updated successfully"
}




-----------------------------------------------------------
localhost:8000/api/doctor/register
{
    "name": "helper",
    "mobile_number": "123987456",
    "email": "helper@test.com",
    "password_hash": "helper",
    "gender": "male",
    "year_of_experience": 15
}

localhost:8000/api/patient/register
{
    "name": "helper",
    "mobile_number": "123987456",
    "email": "helper@test.com",
    "password_hash": "helper",
    "gender": "male"
}
localhost:8000/api/doctor
localhost:8000/api/patient
localhost:8000/api/all-users

localhost:8000/api/doctor/12
localhost:8000/api/patient/5

localhost:8000/auth/login
localhost:8000/auth/me

localhost:8000/api/generate-slots
{
  "appointment_type": "phy",
  "start_date": "2025-04-11",
  "end_date": "2025-04-11",
  "start_time": "10:00 AM",
  "end_time": "01:00 PM",
  "duration": 20
}

localhost:8000/api/check-available-slots [POST]

localhost:8000/api/specific-slot-modification [shift slot]
{
  "id": 370,
  "date": "2025-04-12",
  "time": "12:00 PM"
}

localhost:8000/api/specific-slot-cancel
{
  "ids": [
    370,369
  ]
}

localhost:8000/api/date-slot-cancel

{
  "date": "2025-04-12"
}

localhost:8000/api/slot-telemedicine-physical
{
  "id": 370,
  "appointment_type": "tel"
}

localhost:8000/api/doctor-search/by-department/{{speciality}}[Gynecology]

localhost:8000/api/slots/12/2025-04-13

localhost:8000/api/appointments_new
{
  "appointment_date": "2025-04-13 12:20:00",
  "healthprof": 12
}