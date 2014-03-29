#!/usr/bin/env python3
from plainbox.provider_manager import setup, N_

from manage_ext import setup

setup(
    name='2014.pl.zygoon.examples.go:basic',
    version="1.0",
    description=N_("An example PlainBox provider using the Go programming language"),
    build_cmd="mkdir -p build/bin && cd build/bin && go build ../../src/hello-world.go",
    clean_cmd="rm -rf build/bin",
)
