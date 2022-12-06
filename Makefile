run-debug:
	flask --debug run
run-demo:
	gunicorn3 -e SCRIPT_NAME=/hackaday/tvguide --bind 0.0.0.0:8032 app:app
