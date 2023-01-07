from . import secretstuff
import requests
from pprint import pprint
import logging

api_url = "https://api.imgbb.com/1/upload"


def upload_image(
	image_path,
	user_api_token=None,
	expiration=None,
):

	# If no token provided then use the default one
	if not user_api_token:
		user_api_token = secretstuff.imgbb_api_key

	# Put together the request
	payload = {
		'key': user_api_token,
	}
	if expiration:
		payload['expiration'] = expiration

	with open(image_path, 'rb') as f:
		response = requests.post(
			api_url,
			files={'image': f},
			params=payload
		)

	if response.status_code != 200:
		return False

	image_url = response.json().get('data').get('url')

	return image_url


def api_key_valid(user_api_token):
	if not user_api_token:
		return False

	# Test an image upload
	result = upload_image(
		image_path="test.jpg",
		user_api_token=user_api_token,
		expiration=60
	)

	if not result:
		return False
	return True
