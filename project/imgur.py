import os
import logging
from imgur_python import Imgur
from . import envars

imgur_client = Imgur({'client_id': envars.imgur_client_id})


def upload_image(image_path, delete_after_upload=True):
	try:
		image = imgur_client.image_upload(image_path, 'Untitled', 'An upload from LogLink')
		image_id = image['response']['data']['id']
	except Exception as e:
		logging.error("Error uploading to imgur", str(e))
		return False

	print (image['response'])

	if image['response']['data']['link']:
		# Delete the local file
		if delete_after_upload:
			if os.path.exists(image_path):
				os.remove(image_path)

		return image['response']['data']['link']

	else:
		return None
