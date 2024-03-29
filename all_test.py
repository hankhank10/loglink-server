import pytest
import logging
from pprint import pprint
import requests

from project import app
from project import telegram
from project import envars

from project import User, Message

import base64

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


def check_internet_connection():
    # None of these tests will run correctly if the internet is not corrected
    r = requests.get("https://www.google.com")
    if r.status_code == 200:
        return True
    return False


is_internet_connected = check_internet_connection()


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


list_of_admin_get_routes_to_check = [
    '/admin',
    '/admin/health',
    '/admin/beta_codes'
]

# In the later tests we will be using valid and invalid credentials
valid_credentials = base64.b64encode(
    f'{envars.admin_username}:{envars.admin_password}'.encode('utf-8')).decode('utf-8')
invalid_credentials = base64.b64encode(
    b'admin:wrong_password').decode('utf-8')

# We will test that it is not possible to send a message with a nonexistent ID
nonsense_id = "an_id_that_definitely_does_not_exist"


def test_maximum_input_length():
    # Create a very long message (e.g., 1000 characters)
    long_message = "A" * 10000
    response = send_valid_message(long_message)
    assert response.status_code == 200, "Expected 200 OK but got another response."


def test_admin_get_routes_with_no_security_fail():
    # Check that the admin routes can't be accessed without sending any credentials

    for route in list_of_admin_get_routes_to_check:
        with app.test_client() as client:
            response = client.get(
                route
            )
            assert response.status_code == 401 or response.status_code == 400


def test_admin_get_routes_with_bad_security_fail():
    # Check that the admin routes can't be accessed without the right credentials

    for route in list_of_admin_get_routes_to_check:
        with app.test_client() as client:
            response = client.get(
                route,
                headers={"Authorization": f"Basic {invalid_credentials}"}
            )
            assert response.status_code == 401 or response.status_code == 400


def test_admin_get_routes_with_good_security_pass():
    # Check that the admin routes can be accessed with the right password

    # Encode the correct credentials for authentication
    credentials = base64.b64encode(
        f'{envars.admin_username}:{envars.admin_password}'.encode('utf-8')).decode('utf-8')

    for route in list_of_admin_get_routes_to_check:
        with app.test_client() as client:
            response = client.get(
                route,
                headers={"Authorization": f"Basic {valid_credentials}"}
            )
            assert response.status_code == 200


def test_beta_code_security_post_fail():
    # Check that beta codes can't be added without the right password
    with app.test_client() as client:
        credentials = base64.b64encode(b'admin:wrong_password').decode('utf-8')
        response = client.post(
            '/admin/beta_codes',
            headers={"Authorization": f"Basic {invalid_credentials}"},
            json={"number_of_codes": 1}
        )
        assert response.status_code == 401


def test_beta_code_valid():
    # Check that a beta code can be created when the password is valid

    with app.test_client() as client:
        response = client.post(
            '/admin/beta_codes',
            headers={"Authorization": f"Basic {valid_credentials}"},
            json={"number_of_codes": 1}
        )
        assert response.status_code == 200
        code_added = response.json["codes_added"][0]

    # Check that the beta code is valid
    response = project.use_beta_code(code_added)
    assert response is True


def test_beta_code_not_string_fail():
    # Check that a beta code can't be created when the number of codes is not a string
    with app.test_client() as client:
        response = client.post(
            '/admin/beta_codes',
            headers={"Authorization": f"Basic {valid_credentials}"},
            json={"number_of_codes": "not_a_number"}
        )
        assert response.status_code == 400
        assert b'error' in response.data


def test_get_new_messages_fail():
    # Check that a response with a nonsense id fails
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": nonsense_id,
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
            headers={"Authorization": f"Basic {valid_credentials}"},
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
    # Check that a response with a nonsense id fails
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": nonsense_id,
            }
        )
        assert response.status_code == 404
        assert b'error' in response.data


def test_dummy_message_receive_pass():
    # Check that a dummy message is received
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": "dummy",
            }
        )
        assert response.status_code == 200


def test_retrieve_message_valid():
    # Check that the message can be retrieved
    with app.test_client() as client:
        response = client.post(
            '/get_new_messages/',
            json={
                "user_id": user_token,
            }
        )

        pprint(response.json)

        assert response.status_code == 200
        assert response.json["messages"]["count"] >= 1
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
