#!/bin/bash
set +e
ruff check .
mypy src/
