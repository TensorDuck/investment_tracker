.PHONY: gcp-build, gcp-app, \
deploy, dist, clean-dist, lint

-include .env

#note, containing grc.io tells docker push what address to push the image to
PROJECT_TAG=gcr.io/$(PROJECT_NAME)/investment_tracker-$(VERSION)

gcp-build:
	docker build --build-arg AV_API_KEY=$(AV_API_KEY) --tag $(PROJECT_TAG) .

gcp-app: gcp-build
	set PORT 8080 && docker run --name gcp-app-dev --rm -d -p 9090:8080 -e PORT=8080 $(PROJECT_TAG)

gcp-upload: gcp-build
	docker push $(PROJECT_TAG)

lint:
	black investment_tracker
	isort investment_tracker

deploy: dist
	aws lambda update-function-code --function-name $(LAMBDA_ARN) --zip-file fileb://package.zip

dist: clean-dist
	# make the distribution directory
	mkdir -p dist/
	mkdir -p dist/investment_tracker

	# cp over the relevant files
	touch dist/investment_tracker/__init__.py
	cp -r investment_tracker/aws_deploy dist/investment_tracker
	cp investment_tracker/common.py dist/investment_tracker

	# pip install the relevant packages
	pip install -r requirements-aws.txt -t dist/

	# make the zip file, must be in one-line for makefile to work
	cd dist/; zip -r ../package.zip .

clean-dist:
	rm -rf dist
	rm package.zip