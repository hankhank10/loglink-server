import pytest

from project import app


def test_index():
	client = app.test_client()
	resp = client.get('/')
	assert resp.status_code == 200