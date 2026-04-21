import os
import logging
import requests
from time import sleep
from flask import url_for, current_app
from app.models import NewsletterSubscriber
from app.newsletter.utils import generate_unsubscribe_token

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
logging.basicConfig(level=logging.INFO)


def get_active_subscribers():
    """Fetch all active newsletter subscribers."""
    return NewsletterSubscriber.query.filter_by(is_active=True).all()


def send_new_post_notification(post, retries=2, delay=2):
    """
    Sends a new post notification email to all active subscribers.

    Args:
        post: The Post object to send notifications for.
        retries: Number of retry attempts for failed emails.
        delay: Delay in seconds between retries.

    Returns:
        dict: {"success": int, "failed": list}
    """
    subscribers = get_active_subscribers()
    failed = []

    if not subscribers:
        logging.warning("No active subscribers found.")
        return {"success": 0, "failed": failed}

    # Load environment variables
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("MAIL_DEFAULT_SENDER")

    if not api_key or not sender_email:
        logging.error("BREVO_API_KEY or MAIL_DEFAULT_SENDER is missing in environment.")
        return {"success": 0, "failed": [s.email for s in subscribers]}

    sender_email = sender_email.strip()
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    with current_app.app_context():
        for subscriber in subscribers:
            if not subscriber.email:
                failed.append("Invalid email")
                continue

            # Generate unsubscribe link
            token = generate_unsubscribe_token(subscriber.email)
            unsubscribe_link = url_for("newsletter.unsubscribe", token=token, _external=True)
            post_link = url_for("main.post_detail", slug=post.slug, _external=True)

            html_content = f"""
            <h2>{post.title}</h2>
            <p>{post.excerpt or ''}</p>
            <p><a href="{post_link}">Read Full Post</a></p>
            <hr>
            <small><a href="{unsubscribe_link}">Unsubscribe</a></small>
            """

            data = {
                "sender": {"name": "R2 System Solution Ltd", "email": sender_email},
                "to": [{"email": subscriber.email}],
                "subject": f"New Post: {post.title}",
                "htmlContent": html_content
            }

            attempt = 0
            while attempt <= retries:
                try:
                    response = requests.post(BREVO_URL, headers=headers, json=data, timeout=10)
                    if response.status_code in (200, 201, 202):
                        logging.info(f"Email sent successfully to {subscriber.email}")
                        break  # success, exit retry loop
                    else:
                        logging.warning(f"Failed response ({response.status_code}) for {subscriber.email}: {response.text}")
                        attempt += 1
                        if attempt <= retries:
                            sleep(delay)
                except Exception as e:
                    logging.exception(f"Error sending to {subscriber.email}")
                    attempt += 1
                    if attempt <= retries:
                        sleep(delay)
            else:
                failed.append(subscriber.email)

    success_count = len(subscribers) - len(failed)
    logging.info(f"Emails sent: {success_count}, Failed: {len(failed)}")

    return {"success": success_count, "failed": failed}