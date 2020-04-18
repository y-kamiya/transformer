#!/bin/bash

git submodule update --init

pushd sentencepiece

mkdir build
cd build
cmake ..
make -j 4

popd sentencepiece

