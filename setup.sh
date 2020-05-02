#!/bin/bash

IS_CPU=$1

git submodule update --init

pushd sentencepiece
mkdir build
cd build
cmake ..
make -j 4
popd

if [ ! -d venv-transformer ]; then
    python3 -m venv venv-transformer 
fi
source venv-transformer/bin/activate

pip install torch==1.4.0 torchvision==0.5.0 tensorboard==2.2.0 nltk==3.4.5

pushd apex
git checkout 11faaca7c8ff7a7ba6d55854a9ee2689784f7ca5
if $IS_CPU; then
    pip install -v --no-cache-dir --global-option="--cpp_ext" ./
else
    pip install -v --no-cache-dir --global-option="--cpp_ext" --global-option="--cuda_ext" ./
fi
popd

