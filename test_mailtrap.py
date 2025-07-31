from email_utils import send_mailtrap_email

subject = "📬 Mailtrap Test Email"
body_html = "<p>This is a test email sent from <strong>email_utils.py</strong>.</p>"

send_mailtrap_email(subject, body_html)