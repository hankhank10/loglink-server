# This library handles sending email messages to onboard new users

from redmail import EmailSender
import logging

from project import envars

email_setting_from_address = "admin@loglink.it"
email_setting_host = envars.email_setting_host
email_setting_port = envars.email_setting_port
email_setting_username = envars.email_setting_username
email_setting_password = envars.email_setting_password

email_client = EmailSender(
    host=email_setting_host,
    port=email_setting_port,
    username=email_setting_username,
    password=email_setting_password,
)


def send_email(
    to_email,
    subject,
    body
):

    email_client.send(
        sender=email_setting_from_address,
        receivers=[to_email],
        subject=subject,
        text=body
    )


def send_onboarding_email(
    to_email,
    beta_code
):

    subject = "Welcome to LogLink"
    body = f"""
Thanks for your interest in LogLink.

I am now ready to begin a very small alpha test for the Telegram version of the app. All of the details of how to get set up are available at https://loglink.it/ 

If you want to sign up then you can use the following beta access code {beta_code}

One really important thing that you need to be clear on before you start is that you've read and understood the important security notice at https://loglink.it/security-notice/ - this isn't just the usual disclaimer stuff.

Please do let me know any issues you have either by email, or preferably by raising a github issue at https://github.com/hankhank10/loglink-server/issues

Thanks!"""

    try:
        send_email(
            to_email=to_email,
            subject=subject,
            body=body
        )
        return True
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        return False
