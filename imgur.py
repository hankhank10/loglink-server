import os
from imgur_python import Imgur
from secretstuff import imgur_client_id, imgur_client_secret

imgur_client = Imgur({'client_id': imgur_client_id})


def upload_image(image_path, delete_after_upload=True):
	image = imgur_client.image_upload(image_path, 'Untitled', 'An upload from LogLink')
	image_id = image['response']['data']['id']

	if image['response']['data']['link']:

		# Delete the local file
		if delete_after_upload:
			if os.path.exists(image_path):
				os.remove(image_path)

		return image['response']['data']['link']



	else:
		return None
