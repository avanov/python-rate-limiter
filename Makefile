# https://www.gnu.org/software/make/manual/html_node/Special-Variables.html
# https://ftp.gnu.org/old-gnu/Manuals/make-3.80/html_node/make_17.html
# A few helper entrypoint variables that allow for operating with absolute paths only.
# Ideally, you should always rely on absolute paths in your build commands.
PROJECT_MKFILE_PATH       	:= $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
PROJECT_MKFILE_DIR        	:= $(shell cd $(shell dirname $(PROJECT_MKFILE_PATH)); pwd)

PROJECT_NAME              	:= rate_limiter
PROJECT_ROOT              	:= $(PROJECT_MKFILE_DIR)
PROJECT_COMPILED_SETTINGS	:= $(PROJECT_ROOT)/.env

BUILD_DIR                 	:= $(PROJECT_ROOT)/build
DIST_DIR                  	:= $(PROJECT_ROOT)/dist

DOTENV						:= $(shell which dotenv)
DOTENV_ARGS					:= -f $(PROJECT_COMPILED_SETTINGS)
CMD_WITH_ENV            	:= $(DOTENV) $(DOTENV_ARGS)

############################################################################################

# Updates python dependencies
.PHONY: update
update:
	python -m pip install -U pip
	python -m pip install -r $(PROJECT_ROOT)/requirements/minimal.txt
	python -m pip install -r $(PROJECT_ROOT)/requirements/test.txt
	python -m pip install -r $(PROJECT_ROOT)/requirements/extras/third_party.txt
	python -m pip install -e $(PROJECT_ROOT)


# Runs the entire project's test suite
.PHONY: test
test:
	$(CMD_WITH_ENV) python -- -m pytest 	\
		-s $(PROJECT_ROOT)/tests/			\
		--cov=$(PROJECT_NAME)				\
		--hypothesis-show-statistics


# Runs MyPy typechecks. This isn't part of test suite because type inference is still limited with MyPy
# But it's good to keep around for improvement
.PHONY: typecheck
typecheck:
	mypy --config-file $(PROJECT_ROOT)/setup.cfg --package $(PROJECT_NAME) --install-types


# Produces python source and wheel distributions of the project
.PHONY: release-dist
release-dist: test
	rm -rf $(BUILD_DIR) $(DIST_DIR)
	python $(PROJECT_ROOT)/setup.py sdist bdist_wheel


.PHONY: code-format
code-format:
	black --skip-string-normalization $(PROJECT_ROOT)/$(PROJECT_NAME) $(PROJECT_ROOT)/tests
