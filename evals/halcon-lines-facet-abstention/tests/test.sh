#!/bin/sh
set -eu
test -s /app/evidence/lines_facet_example.hdev
test ! -e /app/evidence/lines_facet_reference.md
