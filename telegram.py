import logging
import secrets
import requests
import pprint # for debug
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response

from __main__ import app
from __main__ import random_token
from __main__ import add_new_message, compose_location_message_contents, compose_image_message_contents

from __main__ import db
from __main__ import User

from __main__ import whitelist_only, message_string, media_uploads_folder

from __main__ import send_message
from __main__ import onboarding_workflow

from __main__ import help_send_token_reminder, help_send_new_token, help_more_help
from __main__ import app_uri

import secretstuff

telegram_base_api_url = 'https://api.telegram.org'
telegram_api_url = f"{telegram_base_api_url}/{secretstuff.telegram_full_token}"

provider = 'telegram'

command_list = [
	'/start',
    "/help",
    "/token",
	"/token_reminder",
    "/refresh",
	"/token_refresh",
	"/more_help",
    "/readme"
]


def download_file_from_telegram(
	file_path,
	extension="jpg",
	save_name=None
):

	if not save_name:
		save_name = secrets.token_hex(16) + "." + extension

	# Download the image
	url = f"{telegram_base_api_url}/file/{secretstuff.telegram_full_token}/{file_path}"
	print(url)
	r = requests.get(url)

	print (r)

	if r.status_code == 200:
		file_save_path = f"{media_uploads_folder}/{save_name}"
		print (file_save_path)
		with open(file_save_path, 'wb') as f:
			f.write(r.content)

		return save_name
	else:
		return False


def send_telegram_message(
	telegram_chat_id,
	message_contents
):
	payload = {
		'chat_id': telegram_chat_id,
		'text': message_contents,
	}
	url = telegram_api_url + '/sendMessage'
	response = requests.post(url, json=payload)

	print ("Message sent to " + url + " response code was " + str(response.status_code))

	if response.status_code == 200:
		return True
	else:
		return False


@app.route('/telegram/webhook/', methods=['POST'])
def telegram_webhook():

	if request.method == 'POST':
		# Get the message from the user
		data = request.get_json()

		# Start putting the mandatory fields into the message_received dictionary, return an error if there's a problem
		try:
			message_received = {
				'telegram_message_id': data['message']['message_id'],
				'telegram_chat_id': data['message']['chat']['id'],
				'mobile': data['message']['from']['id'],
			}
		except:
			print ("Error parsing JSON")
			return "Error: Telegram message missing mandatory fields"

		# Check if this is a new user
		user = User.query.filter_by(provider_id=message_received['telegram_chat_id']).first()

		# If it is a new user, create the account and return the token
		if not user:

			onboarding_result = onboarding_workflow(
				provider=provider,
				provider_id=message_received['telegram_chat_id'],
			)

			if onboarding_result:
				return "ok"
			else:
				return "error"

		# If it's not a new user, process the image and add it to the database
		if user:

			# Work out the message type and get the relevant information
			result = False

			#pprint.pprint(data['message'])

			if 'text' in data['message']:
				message_received['message_type'] = 'text'
				message_received['message_contents'] = data['message']['text']

				# Check if this is a command
				if message_received['message_contents'] in command_list:
					if message_received['message_contents'] == '/start':
						result = onboarding_result = onboarding_workflow(
							provider=provider,
							provider_id=message_received['telegram_chat_id'],
						)

					if message_received['message_contents'] == '/help':
						result = send_message(
							provider,
							message_received['telegram_chat_id'],
							"You can use the following commands to seek help:\n\n/token_reminder - Send yourself a reminder of your token\n/token_refresh - Generate a new token and send it to yourself\n/more_help - Get more help \n\nThe full instructions are at "+ app_uri
						)

					if message_received['message_contents'] == '/token' or message_received['message_contents'] == '/token_reminder':
						help_send_token_reminder(user.id, provider, message_received['telegram_chat_id'])

					if message_received['message_contents'] == '/refresh' or message_received['message_contents'] == '/token_refresh':
						help_send_new_token(user.id, provider, message_received['telegram_chat_id'])

					if message_received['message_contents'] == "/more_help":
						help_more_help(user.id, provider, message_received['telegram_chat_id'])


				else:
					# Add the message to the database
					result = add_new_message(
						user_id=user.id,
						provider=provider,
						message_contents=message_received['message_contents'],
						provider_message_id=message_received['telegram_message_id'],
					)

			elif 'photo' in data['message'] or 'video' in data['message']:

				if 'photo' in data['message']:
					message_received['message_type'] = 'photo'
					message_received['file_id'] = data['message']['photo'][-1]['file_id']

				if 'video' in data['message']:
					message_received['message_type'] = 'video'
					message_received['file_id'] = data['message']['video']['file_id']
					message_received['file_name'] = f"{secrets.token_hex(6)}{['message']['video']['file_name']}"

				# Get the caption if there is one
				if 'caption' in data['message']:
					message_received['caption'] = data['message']['caption']
				else:
					message_received['caption'] = None

				# Download the file from telegram

				# Get the file path from the Telegram API
				r = requests.get(telegram_api_url + '/getFile?file_id=' + message_received['file_id'])
				message_received['file_path'] = r.json()['result']['file_path']

				# Download the file from Telegram

				if message_received['message_type'] == 'photo':
					download_result = download_file_from_telegram(
						file_path=message_received['file_path'],
						extension="jpg",
					)
				if message_received['message_type'] == 'video':
					download_result = download_file_from_telegram(
						file_path=message_received['file_path'],
						save_name=message_received['file_name'],
					)

				if download_result:
					message_received['local_file_name'] = download_result
					message_received['local_file_path'] = f"{media_uploads_folder}/{download_result}"

					# Add the message to the database
					message_received['message_contents'] = compose_image_message_contents(
						image_file_path=message_received['local_file_path'],
						caption=message_received['caption']
					)
					if message_received['message_contents']:
						result = add_new_message(
							user_id=user.id,
							provider=provider,
							message_contents=message_received['message_contents'],
							provider_message_id=message_received['telegram_message_id']
						)
					else:
						logging.error("Failed to upload image to imgur")
				else:
					logging.error("Error downloading file from Telegram")

			if 'location' in data['message']:
				message_received['message_type'] = 'location'
				message_received['location_latitude'] = data['message']['location']['latitude']
				message_received['location_longitude'] = data['message']['location']['longitude']

				#pprint.pprint (data['message']['location'])

				if "venue" in data['message']:
					message_received['location_title'] = data['message']['venue'].get('title')
					message_received['location_address'] = data['message']['venue'].get('address')
				else:
					message_received['location_title'] = None
					message_received['location_address'] = None

				# Add the message to the database
				message_received['message_contents'] = compose_location_message_contents(
					location_latitude=message_received['location_latitude'],
					location_longitude=message_received['location_longitude'],
					location_name=message_received['location_title'],
					location_address=message_received['location_address']
				)

				result = add_new_message(
					user_id=user.id,
					provider=provider,
					message_contents=message_received['message_contents'],
					provider_message_id=message_received['telegram_message_id'],
				)

			else:
				pprint.pprint (data['message'])

			# If message type has not been set then return an error
			if result:
				logging.info("Message added to database")
				return "ok"
			else:
				logging.error("Failed to add message to database")
				send_message(provider, message_received['telegram_chat_id'], message_string["error_with_message"])
				return "Failed to add message to database"

			return "ok"
