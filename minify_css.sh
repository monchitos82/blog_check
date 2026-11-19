#!/usr/bin/env bash

sed -e 's/\/\*.*\*\///g' -e 's/[[:space:]]\+/ /g' style.css | tr -d '\n' > style.min.css
