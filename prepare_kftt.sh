#!/bin/bash

data_dir=$1

script_dir=$(cd `dirname $0`; pwd)
url="http://www.phontron.com/kftt/download/kftt-data-1.0.tar.gz"

mkdir -p $data_dir

pushd $data_dir

if [ ! -f kftt-data-1.0.tar.gz ]; then
    curl -O $url
fi
tar xzvf kftt-data-1.0.tar.gz

ln -s kftt-data-1.0/data/orig/kyoto-train.ja train.orig.ja
ln -s kftt-data-1.0/data/orig/kyoto-train.en train.orig.en

ln -s kftt-data-1.0/data/orig/kyoto-dev.ja valid.orig.ja
ln -s kftt-data-1.0/data/orig/kyoto-dev.en valid.orig.en

ln -s kftt-data-1.0/data/orig/kyoto-test.ja test.orig.ja
ln -s kftt-data-1.0/data/orig/kyoto-test.en test.orig.en

popd

$script_dir/create_dataset.sh $data_dir ja en 8000 0 64


