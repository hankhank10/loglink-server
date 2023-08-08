import pytest
import logging

from project import app
from project import telegram
from project import envars

from project import User, Message

import project
from random import randint

from project import db

user_token = None

telegram_webhook = {
    "message": {
        "chat": {
            "first_name": "Test",
            "id": randint(100000000, 999999999),
            "last_name": "User",
            "type": "private",
            "username": "testuser"
        },
        "date": 1673114415,
        "from": {
            "first_name": "Test",
            "id": 5729547298,
            "is_bot": False,
            "language_code": "en",
            "last_name": "User",
            "username": "testuser"
        },
        "message_id": randint(100, 999),
        "text": "A sample Telegram webhook which hasn't been modified yet"
    },
    "update_id": randint(100000000, 999999999),
}


# A utility function to send a message
def send_valid_message(
    message_text: str = "A sample Telegram webhook",
):
    # Send a valid webhook simulating a new message
    telegram_webhook["message"]["text"] = message_text
    with app.test_client() as client:
        response = client.post(
            '/telegram/webhook/',
            headers={
                "X-Telegram-Bot-Api-Secret-Token": envars.telegram_webhook_auth},
            json=telegram_webhook
        )
        return response


def test_maximum_input_length():
    # Create a very long message (e.g., 1000 characters)
    long_message = "A" * 10000
    response = send_valid_message(long_message)
    assert response.status_code == 200, "Expected 200 OK but got another response."


def test_index_get_ok():
    # Check that the API is running
    with app.test_client() as client:
        response = client.get('/')
        assert response.status_code == 200
        assert b'API is running' in response.data


def test_index_post_fail():
    # Check that the index page is NOT working with a POST request
    with app.test_client() as client:
        response = client.post('/')
        assert response.status_code == 405
        assert b'API is running' not in response.data


def test_beta_code_security_get_fail():
    # Check that beta codes can't be read without the right password
    with app.test_client() as client:
        response = client.get(
            '/admin/beta_codes',
            headers={"admin-password": "wrong_password"}
        )
        assert response.status_code == 401
        assert b'error' in response.data


def test_beta_code_security_post_fail():
    # Check that beta codes can't be added without the right password
    with app.test_client() as client:
        response = client.post(
            '/admin/beta_codes',
            headers={"admin-password": "wrong_password"},
            json={"number_of_codes": 1}
        )
        assert response.status_code == 401
        assert b'error' in response.data


def test_beta_code_valid():
    # Check that a beta code can be created when the password is valid
    with app.test_client() as client:
        response = client.post(
            '/admin/beta_codes',
            headers={"admin-password": envars.admin_password},
            json={"number_of_codes": 1}
        )
        assert response.status_code == 200
        code_added = response.json["codes_added"][0]

    # Check that the beta code is valid
    response = project.use_beta_code(code_added)
    assert response is True


def test_get_new_messages_fail():
    # Check that a nonsense response fails
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": "an_id_that_definitely_does_not_exist",
            }
        )
        assert response.status_code == 404
        assert b'error' in response.data


def test_telegram_webhook_security():
    # Check that the webhook can't be accessed without the right Telegram secret token
    with app.test_client() as client:
        response = client.post(
            '/telegram/webhook/',
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_token"},
            json=telegram_webhook
        )
        assert response.status_code == 401
        assert b'error' in response.data


def test_create_user_valid():
    global telegram_webhook
    global user_token

    # Create a beta code
    with app.test_client() as client:
        response = client.post(
            '/admin/beta_codes',
            headers={"admin-password": envars.admin_password},
            json={"number_of_codes": 1}
        )
        assert response.status_code == 200
        code_added = response.json["codes_added"][0]

    # Send a valid webhook simulating a new user
    telegram_webhook["message"]["text"] = "/start " + code_added
    with app.test_client() as client:
        response = client.post(
            '/telegram/webhook/',
            headers={
                "X-Telegram-Bot-Api-Secret-Token": envars.telegram_webhook_auth},
            json=telegram_webhook
        )
        assert response.status_code == 200

    # Check the created user is in the database
    user = User.query.filter_by(
        provider_id=telegram_webhook["message"]["chat"]["id"]
    ).first()
    assert user is not None

    user_token = user.token


def test_create_new_message_valid():
    global telegram_webhook

    # Send a valid webhook simulating a new message
    response = send_valid_message("A sample Telegram webhook")
    assert response.status_code == 200

    # Check the created message is in the database
    messages = User.query.filter_by(
        token=user_token
    ).first().messages
    assert len(messages) == 1


def test_retrieve_message_fail():
    # Check that a nonsense response fails
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": "an_id_that_definitely_does_not_exist",
            }
        )
        assert response.status_code == 404
        assert b'error' in response.data


def test_retrieve_message_valid():
    # Check that the message can be retrieved
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": user_token,
            }
        )
        assert response.status_code == 200
        assert response.json["messages"]["count"] == 1
        assert response.json["messages"]["contents"][0]["contents"] == telegram_webhook["message"]["text"]


def test_message_only_delivered_once():
    # Check that the message has been deleted
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": user_token,
            }
        )
        assert response.status_code == 200
        assert response.json["messages"]["count"] == 0


def test_message_has_been_deleted():
    # Check that the message has been deleted
    messages = User.query.filter_by(
        token=user_token
    ).first().messages
    assert len(messages) == 0
