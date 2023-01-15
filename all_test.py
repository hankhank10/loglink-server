import pytest

from project import app
from project import telegram


def test_index():
	# Check that the API is running
	with app.test_client() as client:
		response = client.get('/')
		assert response.status_code == 200
		assert b'API is running' in response.data

	with app.test_client() as client:
		response = client.post('/')
		assert response.status_code == 405
		assert b'API is running' not in response.data


def test_beta_codes():
	# Check that beta codes can't be read without the right password
	with app.test_client() as client:
		response = client.get(
			'/admin/beta_codes',
			headers={"admin-password": "wrong_password"}
		)
		assert response.status_code == 401
		assert b'error' in response.data

	# Check that beta codes can't be added without the right password
	with app.test_client() as client:
		response = client.post(
			'/admin/beta_codes',
			headers={"admin-password": "wrong_password"},
			json={"number_of_codes": 1}
		)
		assert response.status_code == 401
		assert b'error' in response.data

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


def test_get_new_messages():
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


