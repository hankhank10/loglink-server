import pytest
import logging

from project import app
from project import telegram
from project import envars

import project
from random import randint


def test_index_get_ok():
	# Check that the API is running
	with app.test_client() as client:
		response = client.get('/')
		assert response.status_code == 200
		assert b'API is running' in response.data


def test_index_post_fail():
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
		"message_id": randint(100,999),
		"text": "A sample Telegram webhook"
	},
	"update_id": randint(100000000, 999999999),
}

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

	# Create a beta code
	with app.test_client() as client:
		response = client.post(
			'/admin/beta_codes',
			headers={"admin-password": envars.admin_password},
			json={"number_of_codes": 1}
		)
		assert response.status_code == 200
		code_added = response.json["codes_added"][0]
		print(code_added)

	# Send a valid webhook simulating a new user
	telegram_webhook["message"]["text"] = "/start " + code_added
	with app.test_client() as client:
		response = client.post(
			'/telegram/webhook/',
			headers={"X-Telegram-Bot-Api-Secret-Token": envars.telegram_webhook_auth},
			json=telegram_webhook
		)
		assert response.status_code == 200

