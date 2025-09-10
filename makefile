install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-webui:
	pip install -e ".[webui]"

run:
	digink '/home/nitz/Pictures/Wallpapers/keepers/Oculus_Wallpaper_2560x1600.png'

run-debug:
	mkdir -p debug
	digink '/home/nitz/Pictures/Wallpapers/keepers/Oculus_Wallpaper_2560x1600.png' --debug-output-dir debug

run-webui:
	digink-webui

clean:
	rm -rf build/ dist/ src/*.egg-info/ debug/

test:
	pytest

lint:
	black src/
	flake8 src/

type-check:
	mypy src/

deploy:
	rsync -avz --delete --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' --exclude='.sl' --exclude='debug/' --exclude='build/' --exclude='dist/' --exclude='src/*.egg-info/' . digink:./controller/

