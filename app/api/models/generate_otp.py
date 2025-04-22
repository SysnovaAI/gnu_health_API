import random
from sqlalchemy import text
from sqlalchemy.orm import Session

def otp_generator():
    while True:
        yield random.randint(100000, 999999)  # Always 6-digit

def generate_secure_otp(db: Session, user_id):
    """
    Generate OTP and update it in the database for a specific user along with the current server time.

    Parameters:
    db (Session): SQLAlchemy database session object.
    user_id (int): ID of the user to whom the OTP is assigned.
    """
    try:
        # Generate OTP
        otp = next(otp_generator())

        # Get current server time in Asia/Dhaka timezone
        server_time_query = text("SELECT NOW() AT TIME ZONE 'Asia/Dhaka';")
        server_time_result = db.execute(server_time_query)
        current_time = server_time_result.fetchone()

        # Update user's OTP and generation time
        otp_update_query = text("""
            UPDATE res_user
            SET otp_number = :otp,
                otp_date = :otp_generate_time
            WHERE id = :user_id
        """)
        db.execute(otp_update_query, {
            "otp": otp,
            "otp_generate_time": current_time[0],
            "user_id": user_id
        })

        # Optional sleep (e.g., for testing OTP expiry)
        # sleep(30)  # Uncomment if needed

        db.commit()

        return otp  # Optionally return the OTP if you need it

    except Exception as e:
        db.rollback()
        raise e

