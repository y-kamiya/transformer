#!/bin/bash

name=$1
src=${2:-en}
tgt=${3:-fr}
vocab_size=${4:-1000}
valid_count=${5:-1000}

script_dir=$(cd `dirname $0`; pwd)
data_dir=$script_dir/data/$name

function build()
{
    lang=$1
    valid_count=$2
    data_dir=$3
    name=$4

    ./sentencepiece/build/src/spm_encode --model=$data_dir/$name.model --output_format=id < $data_dir/train.orig.$lang > $data_dir/a.tmp

    # add BOS and EOS
    sed -e 's/^/1 /' -e 's/$/ 2/' $data_dir/a.tmp > $data_dir/b.tmp

    # separate data for train and valid
    head -n $valid_count $data_dir/b.tmp > $data_dir/valid.$lang
    sed -e "1,${valid_count}d" $data_dir/b.tmp > $data_dir/train.$lang

    # use tmp file to avoid using 'sed -i' because usage is different between GNU and BSD
    rm -f $data_dir/*.tmp
}

pushd $script_dir

cat $data_dir/train.orig.$src $data_dir/train.orig.$tgt > $data_dir/spm_input
./sentencepiece/build/src/spm_train --input=$data_dir/spm_input --model_prefix=$name --vocab_size=$vocab_size --pad_id=3

mv $name.model $name.vocab $data_dir/

build $src $valid_count $data_dir $name
build $tgt $valid_count $data_dir $name

popd

