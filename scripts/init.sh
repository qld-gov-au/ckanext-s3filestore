#!/usr/bin/env bash

CLICK_ARGS="--yes" ./scripts/ckan_cli db clean
CKAN_INI=test.ini ./scripts/ckan_cli db init