# Configuration
REMOTE_HOST = digink.lan

help:
	@echo "Available targets:"
	@echo "  test              - Run tests with pytest"
	@echo "  lint              - Run code formatting and linting"
	@echo "  deploy            - Deploy to remote server (files only)"
	@echo "  remote-install    - Install dependencies on remote server"
	@echo "  remote-restart    - Restart service on remote server"
	@echo "  big-deploy        - Full deployment: deploy + remote-install + remote-restart"
	@echo "  install-systemd   - Install as systemd service (runs poetry install + systemd setup)"
	@echo "  uninstall-systemd - Remove systemd service"

test:
	poetry run pytest

lint:
	poetry run ruff check --fix src/
	poetry run black src/
	poetry run autoflake8 -ri src/
	poetry run flake8 src/
	poetry run mypy src/

deploy:
	rsync -avz --delete --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' --exclude='.git' --exclude='.sl' --exclude='debug/' --exclude='build/' --exclude='dist/' --exclude='src/*.egg-info/' --exclude='devices.yaml' --exclude='settings.toml' . $(REMOTE_HOST):./controller/

remote-install:
	@echo "Installing dependencies on $(REMOTE_HOST)..."
	ssh $(REMOTE_HOST) "cd ./controller && poetry install"

remote-restart:
	@echo "Restarting tapestry-webui service on $(REMOTE_HOST)..."
	ssh $(REMOTE_HOST) "sudo systemctl restart tapestry-webui"
	ssh $(REMOTE_HOST) "sudo systemctl status tapestry-webui --no-pager"

big-deploy: deploy remote-install remote-restart
	@echo "Big deployment complete!"

install-systemd:
	@echo "Installing Tapestry WebUI as systemd service..."
	# Install dependencies
	poetry install
	# Create systemd unit file from template
	@sed -e 's|USER_PLACEHOLDER|$(USER)|g' \
	     -e 's|WORKING_DIR_PLACEHOLDER|$(PWD)|g' \
	     tapestry-webui.service.template > tapestry-webui.service
	# Copy unit file to systemd directory
	sudo cp tapestry-webui.service /etc/systemd/system/
	# Reload systemd and enable service
	sudo systemctl daemon-reload
	sudo systemctl enable tapestry-webui.service
	@echo "Systemd service installed. Start with: sudo systemctl start tapestry-webui"
	@echo "Check status with: sudo systemctl status tapestry-webui"

uninstall-systemd:
	@echo "Uninstalling Tapestry WebUI systemd service..."
	# Stop and disable service
	-sudo systemctl stop tapestry-webui.service
	-sudo systemctl disable tapestry-webui.service
	# Remove unit file
	-sudo rm /etc/systemd/system/tapestry-webui.service
	# Reload systemd
	sudo systemctl daemon-reload
	@echo "Systemd service uninstalled."


