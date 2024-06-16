#!/bin/bash

aws s3 cp . s3://barlasgarden/music/ --recursive \
--exclude "*" \
--include "index.html" \
--include "*.css" \
--include "*.map"

aws cloudfront create-invalidation \
--distribution-id E55WEWI99JZUV \
--paths /music/index.html /music/pico.min.css /music/pico.min.css.map