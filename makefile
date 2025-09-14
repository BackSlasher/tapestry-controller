test:
	poetry run pytest

lint:
	poetry run black src/
	poetry run flake8 src/
	poetry run mypy src/

deploy:
	rsync -avz --delete --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' --exclude='.git' --exclude='.sl' --exclude='debug/' --exclude='build/' --exclude='dist/' --exclude='src/*.egg-info/' --exclude='devices.yaml' . digink:./controller/

