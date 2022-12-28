from os import path
from imgur_python import Imgur
from secretstuff import imgur_client_id, imgur_client_secret

imgur_client = Imgur({'client_id': imgur_client_id})


def upload_image(image_path):
	image = imgur_client.image_upload(image_filename, 'Untitled', 'My first image upload')
	image_id = image['response']['data']['id']

	if image['response']['data']['link']:
		return image['response']['data']['link']
	else:
		return None
