import requests

import secretstuff

# Import flask
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response

# Create the app
app = Flask(__name__)


@app.route('/', methods=['GET'])
def hello_world():
	return 'Hello, World Telegram!'


# Run the app
if __name__ == "__main__":
	app.run(host='0.0.0.0', port=5010, debug=True)
	