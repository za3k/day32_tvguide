run-debug:
	flask --debug run
run-demo:
	gunicorn3 -e SCRIPT_NAME=/hackaday/tvguide --bind 0.0.0.0:8033 app:app
