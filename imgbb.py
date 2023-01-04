from secretstuff import imgbb_api_key
import requests
import logging

api_url = "https://api.imgbb.com/1/upload"


def upload_image(image_path):
	with open(image_path, 'rb') as f:
		response = requests.post(api_url, files={'image': f}, data={'key': imgbb_api_key})

	if response.status_code != 200:
		return False

	image_url = response.json().get('data').get('url')

	return image_url




